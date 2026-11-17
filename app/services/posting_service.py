import logging

import httpx

from app.config import Settings
from app.platforms.base import Platform, PlatformError, PublishedPost
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.telegram import TelegramPlatform
from app.schemas import PlatformResult

logger = logging.getLogger(__name__)


def build_platforms(settings: Settings) -> list[Platform]:
    return [
        MastodonPlatform(settings),
        BlueskyPlatform(settings),
        DevToPlatform(settings),
        TelegramPlatform(settings),
        DiscordPlatform(settings),
    ]


def result_from_success(platform: Platform, published: PublishedPost) -> PlatformResult:
    timestamp = published.posted_at
    return PlatformResult(
        platform=platform.name,
        status="success",
        posted_url=published.posted_url,
        public_access=published.public_access,
        date=timestamp.date(),
        time=timestamp.time().replace(microsecond=0),
    )


def result_from_failure(platform: Platform, error: Exception) -> PlatformResult:
    return PlatformResult(
        platform=platform.name,
        status="failed",
        error=str(error),
    )


async def publish_to_all(
    message: str,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> list[PlatformResult]:
    platforms = build_platforms(settings)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20.0)
    results: list[PlatformResult] = []

    try:
        for platform in platforms:
            try:
                published = await platform.publish(message, http_client)
                result = result_from_success(platform, published)
            except PlatformError as error:
                results.append(result_from_failure(platform, error))
            except httpx.HTTPError as error:
                logger.warning("%s request failed: %s", platform.name, type(error).__name__)
                results.append(
                    result_from_failure(
                        platform, PlatformError(f"HTTP request failed: {type(error).__name__}")
                    )
                )
            except Exception as error:
                logger.error(
                    "%s failed unexpectedly: %s", platform.name, type(error).__name__
                )
                results.append(
                    result_from_failure(
                        platform, PlatformError(f"Unexpected error: {type(error).__name__}")
                    )
                )
            else:
                results.append(result)
    finally:
        if owns_client:
            await http_client.aclose()

    return results
