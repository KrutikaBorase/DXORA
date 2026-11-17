import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import Settings
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.reddit import RedditPlatform
from app.platforms.telegram import TelegramPlatform
from app.services.posting_service import publish_to_all


MESSAGE = "Visit https://example.com"
PLATFORMS = [
    MastodonPlatform,
    BlueskyPlatform,
    RedditPlatform,
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
        reddit_client_id="test-id",
        reddit_client_secret="test-secret",
        reddit_username="test-user",
        reddit_password="test-password",
        reddit_subreddit="test",
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
    if path == "/api/v1/access_token":
        return httpx.Response(200, json={"access_token": "reddit-token"})
    if path == "/api/submit":
        assert parse_qs(request.content.decode())["text"] == [MESSAGE]
        return httpx.Response(
            200, json={"json": {"errors": [], "data": {"url": "https://reddit.com/r/test/1"}}}
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
        (RedditPlatform, "https://reddit.com/r/test/1", False),
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
@pytest.mark.parametrize("platform_type", [BlueskyPlatform, RedditPlatform, DiscordPlatform])
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
