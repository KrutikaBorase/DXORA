import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import Settings
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.telegram import TelegramPlatform
from app.services.posting_service import publish_to_all


MESSAGE = "Visit https://example.com"
PLATFORMS = [
    MastodonPlatform,
    BlueskyPlatform,
    DevToPlatform,
    TelegramPlatform,
    DiscordPlatform,
]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        mastodon_access_token="test-token",
        bluesky_handle="user.bsky.social",
        bluesky_app_password="test-password",
        devto_api_key="test-key",
        telegram_bot_token="test-token",
        telegram_chat_id="@example",
        discord_webhook_url="https://discord.com/api/webhooks/1/test-token",
    )


def success_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/v1/statuses":
        assert parse_qs(request.content.decode()) == {
            "status": [MESSAGE],
            "visibility": ["public"],
        }
        return httpx.Response(
            200, json={"url": "https://mastodon.social/@user/1", "visibility": "public"}
        )
    if path.endswith("/com.atproto.server.createSession"):
        assert json.loads(request.content)["identifier"] == "user.bsky.social"
        return httpx.Response(200, json={"accessJwt": "jwt", "did": "did:plc:abc"})
    if path.endswith("/com.atproto.repo.createRecord"):
        assert json.loads(request.content)["record"]["text"] == MESSAGE
        return httpx.Response(200, json={"uri": "at://did:plc:abc/app.bsky.feed.post/1"})
    if path.endswith("/app.bsky.feed.getPostThread"):
        assert request.url.params["uri"] == "at://did:plc:abc/app.bsky.feed.post/1"
        return httpx.Response(
            200, json={"thread": {"post": {"uri": "at://did:plc:abc/app.bsky.feed.post/1"}}}
        )
    if path == "/api/articles/1":
        assert "api-key" not in request.headers
        return httpx.Response(
            200, json={"id": 1, "url": "https://dev.to/user/post", "published_at": "2026-11-17T00:00:00Z"}
        )
    if path == "/api/articles":
        assert request.headers["api-key"] == "test-key"
        assert json.loads(request.content)["article"] == {
            "title": "Visit",
            "body_markdown": MESSAGE,
            "published": True,
        }
        return httpx.Response(
            201, json={"id": 1, "url": "https://dev.to/user/post", "published_at": "2026-11-17T00:00:00Z"}
        )
    if path.endswith("/sendMessage"):
        assert json.loads(request.content)["text"] == MESSAGE
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 42,
                    "chat": {"type": "channel", "username": "example"},
                },
            },
        )
    if path.startswith("/api/webhooks/"):
        if request.method == "GET":
            return httpx.Response(200, json={"guild_id": "10"})
        assert json.loads(request.content)["content"] == MESSAGE
        assert request.url.params["wait"] == "true"
        return httpx.Response(200, json={"id": "30", "channel_id": "20"})
    raise AssertionError(f"Unexpected request: {request.method} {path}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform_type", "expected_url", "public_access"),
    [
        (MastodonPlatform, "https://mastodon.social/@user/1", True),
        (BlueskyPlatform, "https://bsky.app/profile/user.bsky.social/post/1", True),
        (DevToPlatform, "https://dev.to/user/post", True),
        (TelegramPlatform, "https://t.me/example/42", True),
        (DiscordPlatform, "https://discord.com/channels/10/20/30", False),
    ],
)
async def test_platform_success(
    settings: Settings, platform_type, expected_url: str, public_access: bool
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(success_response)) as client:
        result = await platform_type(settings).publish(MESSAGE, client)
    assert result.posted_url == expected_url
    assert result.public_access is public_access


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "title"),
    [
        ("https://example.com", "Shared link"),
        ("x" * 100 + " https://example.com", "x" * 80),
    ],
)
async def test_devto_title_does_not_duplicate_cta(
    settings: Settings, message: str, title: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200, json={"id": 1, "url": "https://dev.to/user/post", "published_at": "2026-11-17T00:00:00Z"}
            )
        article = json.loads(request.content)["article"]
        assert article == {"title": title, "body_markdown": message, "published": True}
        return httpx.Response(
            201, json={"id": 1, "url": "https://dev.to/user/post", "published_at": "2026-11-17T00:00:00Z"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DevToPlatform(settings).publish(message, client)
    assert result.posted_url == "https://dev.to/user/post"


@pytest.mark.asyncio
async def test_devto_unpublished_response_is_a_failure(settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.posting_service.build_platforms", lambda _: [DevToPlatform(settings)]
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            201, json={"url": "https://dev.to/user/draft", "published_at": None}
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        result = (await publish_to_all(MESSAGE, settings, client))[0]
    assert result.status == "failed"
    assert result.error == "DEV Community did not confirm a published article URL"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    ["Visit https://example.com.", "Go \u2728 https://example.com/path?a=1,2;b=3!"],
)
async def test_bluesky_adds_clickable_cta_with_utf8_offsets(
    settings: Settings, message: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/com.atproto.server.createSession"):
            return httpx.Response(200, json={"accessJwt": "jwt", "did": "did:plc:abc"})
        if request.url.path.endswith("/app.bsky.feed.getPostThread"):
            return httpx.Response(
                200, json={"thread": {"post": {"uri": "at://did:plc:abc/app.bsky.feed.post/1"}}}
            )
        record = json.loads(request.content)["record"]
        facet = record["facets"][0]
        start = facet["index"]["byteStart"]
        end = facet["index"]["byteEnd"]
        url = facet["features"][0]["uri"]
        assert message.encode("utf-8")[start:end].decode("utf-8") == url
        assert url == message[message.index("https://") : -1]
        assert facet["features"][0]["$type"] == "app.bsky.richtext.facet#link"
        return httpx.Response(200, json={"uri": "at://did:plc:abc/app.bsky.feed.post/1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await BlueskyPlatform(settings).publish(message, client)
    assert result.posted_url == "https://bsky.app/profile/user.bsky.social/post/1"


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_type", [BlueskyPlatform, DevToPlatform])
@pytest.mark.parametrize("failure", ["not_found", "bad_json", "timeout"])
async def test_failed_public_check_does_not_change_posting_success(
    settings: Settings, platform_type, failure: str, caplog
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        is_public_check = (
            request.url.path.endswith("/app.bsky.feed.getPostThread")
            or request.url.path == "/api/articles/1"
        )
        if not is_public_check:
            return success_response(request)
        if failure == "not_found":
            return httpx.Response(404)
        if failure == "bad_json":
            return httpx.Response(200, content=b"not JSON")
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await platform_type(settings).publish(MESSAGE, client)
    assert result.posted_url
    assert result.public_access is False
    assert "visibility could not be confirmed" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_type", PLATFORMS)
@pytest.mark.parametrize("failure", ["unauthorized", "bad_json", "missing_fields", "timeout"])
async def test_platform_failures_are_reported(
    settings: Settings, monkeypatch, platform_type, failure: str
) -> None:
    platform = platform_type(settings)
    monkeypatch.setattr(
        "app.services.posting_service.build_platforms", lambda _: [platform]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "unauthorized":
            return httpx.Response(401, json={"error": "Unauthorized"})
        if failure == "bad_json":
            return httpx.Response(200, content=b"not JSON")
        if failure == "missing_fields":
            return httpx.Response(200, json={})
        raise httpx.ReadTimeout("timeout with secret in URL", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await publish_to_all(MESSAGE, settings, client)

    assert len(results) == 1
    assert results[0].platform == platform.name
    assert results[0].status == "failed"
    assert results[0].error
    assert "secret in URL" not in results[0].error
    if failure == "unauthorized":
        assert "401" in results[0].error


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_type", [BlueskyPlatform, DiscordPlatform])
@pytest.mark.parametrize("failure", ["unauthorized", "bad_json", "missing_fields", "timeout"])
async def test_second_request_failures_are_reported(
    settings: Settings, monkeypatch, platform_type, failure: str
) -> None:
    platform = platform_type(settings)
    monkeypatch.setattr("app.services.posting_service.build_platforms", lambda _: [platform])
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return success_response(request)
        if failure == "unauthorized":
            return httpx.Response(401, json={"error": "Unauthorized"})
        if failure == "bad_json":
            return httpx.Response(200, content=b"not JSON")
        if failure == "missing_fields":
            return httpx.Response(200, json={})
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await publish_to_all(MESSAGE, settings, client)
    assert request_count == 2
    assert results[0].status == "failed"
    assert results[0].error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("visibility", "is_public"),
    [("public", True), ("unlisted", True), ("private", False), ("direct", False)],
)
async def test_mastodon_uses_returned_visibility(
    settings: Settings, visibility: str, is_public: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": "https://example.com/1", "visibility": visibility})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await MastodonPlatform(settings).publish(MESSAGE, client)
    assert result.public_access is is_public


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chat", "expected_url"),
    [
        ({"type": "channel", "username": "public_channel"}, "https://t.me/public_channel/42"),
        ({"type": "supergroup", "username": "public_group"}, "https://t.me/public_group/42"),
        ({"type": "channel"}, None),
        ({"type": "private", "username": "person"}, None),
    ],
)
async def test_telegram_visibility_uses_returned_chat(
    settings: Settings, chat: dict, expected_url: str | None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": True, "result": {"message_id": 42, "chat": chat}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await TelegramPlatform(settings).publish(MESSAGE, client)
    assert result.posted_url == expected_url
    assert result.public_access is (expected_url is not None)
