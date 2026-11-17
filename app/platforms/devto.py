import httpx

from app.config import Settings
from app.links import extract_cta_link
from app.platforms.base import (
    PlatformError,
    PublishedPost,
    now_utc,
    raise_for_platform_response,
)


class DevToPlatform:
    name = "DEV Community"

    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.devto_api_key

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        if not self.api_key:
            raise PlatformError("DEVTO_API_KEY is not configured")

        link = extract_cta_link(message)
        title = (message[:link.start] + message[link.end:]).strip(" \t\r\n-:;,")
        title = title[:80].strip() or "Shared link"
        response = await client.post(
            "https://dev.to/api/articles",
            headers={
                "api-key": self.api_key,
                "accept": "application/vnd.forem.api-v1+json",
            },
            json={
                "article": {
                    "title": title,
                    "body_markdown": message,
                    "published": True,
                }
            },
        )
        raise_for_platform_response(response)
        payload = response.json()
        if not payload.get("url") or not payload.get("published_at"):
            raise PlatformError("DEV Community did not confirm a published article URL")
        return PublishedPost(
            posted_url=payload["url"],
            public_access=True,
            posted_at=now_utc(),
        )
