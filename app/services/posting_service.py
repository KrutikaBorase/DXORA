import httpx

from app.config import Settings
from app.platforms.base import Platform, PlatformError, PublishedPost
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.reddit import RedditPlatform
from app.platforms.telegram import TelegramPlatform
from app.schemas import PlatformResult


def build_platforms(settings: Settings) -> list[Platform]:
    return [
        MastodonPlatform(settings),
        BlueskyPlatform(settings),
        RedditPlatform(settings),
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
            except (PlatformError, httpx.HTTPError) as error:
                results.append(result_from_failure(platform, error))
            else:
                results.append(result_from_success(platform, published))
    finally:
        if owns_client:
            await http_client.aclose()

    return results
