import httpx

from app.config import Settings
from app.platforms.base import (
    PlatformError,
    PublishedPost,
    now_utc,
    raise_for_platform_response,
)


class MastodonPlatform:
    name = "Mastodon"

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.mastodon_api_base_url.rstrip("/")
        self.access_token = settings.mastodon_access_token

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        if not self.access_token:
            raise PlatformError("MASTODON_ACCESS_TOKEN is not configured")

        response = await client.post(
            f"{self.base_url}/api/v1/statuses",
            headers={"Authorization": f"Bearer {self.access_token}"},
            data={"status": message, "visibility": "public"},
        )
        raise_for_platform_response(response)
        payload = response.json()
        return PublishedPost(
            posted_url=payload.get("url"),
            public_access=payload["visibility"] in {"public", "unlisted"},
            posted_at=now_utc(),
        )
