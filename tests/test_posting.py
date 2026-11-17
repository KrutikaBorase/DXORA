import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.platforms.base import PlatformError, PublishedPost
from app.schemas import PostingRequest
from app.services.posting_service import publish_to_all


def test_request_requires_one_valid_cta_link() -> None:
    request = PostingRequest(
        message="Launch update: https://example.com/products"
    )
    assert str(request.message).endswith("products")


@pytest.mark.parametrize(
    "message",
    [
        "Launch update without a link",
        "Two links: https://example.com and https://example.org",
        "Broken link: https://",
        "https://example.com,https://example.org",
        "https://example.com;https://example.org",
        "https://example.com|https://example.org",
        "(https://example.com)(https://example.org)",
        "https://example.com www.example.org",
        "https://example.com,example.org",
        "example.org",
        "https://example.com https://",
        "https://example.com https://example.com",
        "ftp://example.org",
        "www.example.org",
    ],
)
def test_request_rejects_invalid_cta_links(message: str) -> None:
    with pytest.raises(ValueError):
        PostingRequest(message=message)


def test_request_rejects_messages_over_200_characters() -> None:
    with pytest.raises(ValueError):
        PostingRequest(message=("x" * 190) + " https://example.com")


@pytest.mark.parametrize(
    "message",
    ["No link", "https://example.com;https://example.org", "x" * 201],
)
def test_endpoint_returns_validation_error_without_posting(message: str) -> None:
    with TestClient(app) as client:
        response = client.post("/posting", json={"message": message})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "message",
    [
        "Visit https://example.com/path?a=1,2;b=3.",
        "Visit https://example.com/?redirect=https://example.org",
        "Contact us@example.org or visit https://example.com.",
        "x" * (200 - len(" https://example.com")) + " https://example.com",
    ],
)
def test_request_accepts_one_link_with_punctuation(message: str) -> None:
    assert PostingRequest(message=message).message == message


class WorkingPlatform:
    name = "Working"

    async def publish(self, message: str, client: object) -> PublishedPost:
        return PublishedPost(
            posted_url="https://example.com/post/1",
            public_access=True,
            posted_at=datetime(2026, 11, 16, 10, 30, tzinfo=timezone.utc),
        )


class FailingPlatform:
    name = "Failing"

    async def publish(self, message: str, client: object) -> PublishedPost:
        raise PlatformError("credentials are missing")


@pytest.mark.asyncio
async def test_one_platform_failure_does_not_stop_other_platforms(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.posting_service.build_platforms",
        lambda settings: [FailingPlatform(), WorkingPlatform()],
    )

    results = await publish_to_all(
        "Launch update: https://example.com",
        Settings(),
        client=object(),
    )

    assert [result.status for result in results] == ["failed", "success"]
    assert results[0].error == "credentials are missing"
    assert results[1].posted_url == "https://example.com/post/1"


@pytest.mark.asyncio
async def test_unexpected_error_is_isolated_and_logged(monkeypatch, caplog) -> None:
    class BrokenPlatform:
        name = "Broken"

        async def publish(self, message: str, client: object) -> PublishedPost:
            raise KeyError("missing field")

    monkeypatch.setattr(
        "app.services.posting_service.build_platforms",
        lambda settings: [BrokenPlatform(), WorkingPlatform()],
    )
    results = await publish_to_all("Visit https://example.com", Settings(_env_file=None))

    assert [result.status for result in results] == ["failed", "success"]
    assert results[0].error == "Unexpected error: KeyError"
    assert "Broken failed unexpectedly: KeyError" in caplog.text


@pytest.mark.asyncio
async def test_platforms_run_concurrently_and_keep_result_order(monkeypatch) -> None:
    ready = asyncio.Event()
    entered: list[str] = []

    class WaitingPlatform:
        def __init__(self, name: str, fail: bool = False) -> None:
            self.name = name
            self.fail = fail

        async def publish(self, message: str, client: object) -> PublishedPost:
            entered.append(self.name)
            if len(entered) == 3:
                ready.set()
            await ready.wait()
            if self.fail:
                raise PlatformError("Test failure")
            return await WorkingPlatform().publish(message, client)

    monkeypatch.setattr(
        "app.services.posting_service.build_platforms",
        lambda settings: [
            WaitingPlatform("First"),
            WaitingPlatform("Second", fail=True),
            WaitingPlatform("Third"),
        ],
    )
    results = await asyncio.wait_for(
        publish_to_all("Visit https://example.com", Settings(_env_file=None)),
        timeout=2,
    )
    assert [result.platform for result in results] == ["First", "Second", "Third"]
    assert [result.status for result in results] == ["success", "failed", "success"]
