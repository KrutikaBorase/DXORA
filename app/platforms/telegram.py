import httpx

from app.config import Settings
from app.platforms.base import (
    PlatformError,
    PublishedPost,
    now_utc,
    raise_for_platform_response,
)


class TelegramPlatform:
    name = "Telegram"

    def __init__(self, settings: Settings) -> None:
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        if not self.bot_token or not self.chat_id:
            raise PlatformError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are not configured"
            )

        response = await client.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={"chat_id": self.chat_id, "text": message},
        )
        raise_for_platform_response(response)
        payload = response.json()
        if not payload.get("ok"):
            raise PlatformError(payload.get("description", "Telegram rejected message"))

        # Telegram does not expose a public URL for private chats.
        return PublishedPost(
            posted_url=None,
            public_access=False,
            posted_at=now_utc(),
        )
