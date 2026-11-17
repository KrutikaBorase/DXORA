import httpx

from app.config import Settings
from app.platforms.base import (
    PlatformError,
    PublishedPost,
    now_utc,
    raise_for_platform_response,
)


class DiscordPlatform:
    name = "Discord"

    def __init__(self, settings: Settings) -> None:
        self.webhook_url = settings.discord_webhook_url

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        if not self.webhook_url:
            raise PlatformError("DISCORD_WEBHOOK_URL is not configured")

        webhook_response = await client.get(self.webhook_url)
        raise_for_platform_response(webhook_response)
        guild_id = webhook_response.json()["guild_id"]

        response = await client.post(
            f"{self.webhook_url}{'&' if '?' in self.webhook_url else '?'}wait=true",
            json={"content": message},
        )
        raise_for_platform_response(response)
        payload = response.json()
        message_id = payload["id"]
        channel_id = payload["channel_id"]
        posted_url = (
            f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
            if guild_id and channel_id and message_id
            else None
        )
        return PublishedPost(
            posted_url=posted_url,
            public_access=False,
            posted_at=now_utc(),
        )
