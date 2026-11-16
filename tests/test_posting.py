from datetime import datetime, timezone

import pytest

from app.config import Settings
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
    ],
)
def test_request_rejects_invalid_cta_links(message: str) -> None:
    with pytest.raises(ValueError):
        PostingRequest(message=message)


def test_request_rejects_messages_over_200_characters() -> None:
    with pytest.raises(ValueError):
        PostingRequest(message=("x" * 190) + " https://example.com")


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
