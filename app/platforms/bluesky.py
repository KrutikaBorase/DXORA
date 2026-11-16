import httpx

from app.config import Settings
from app.platforms.base import (
    PlatformError,
    PublishedPost,
    now_utc,
    raise_for_platform_response,
)


class BlueskyPlatform:
    name = "Bluesky"

    def __init__(self, settings: Settings) -> None:
        self.pds_url = settings.bluesky_pds_url.rstrip("/")
        self.handle = settings.bluesky_handle
        self.app_password = settings.bluesky_app_password

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        if not self.handle or not self.app_password:
            raise PlatformError(
                "BLUESKY_HANDLE and BLUESKY_APP_PASSWORD are not configured"
            )

        session_response = await client.post(
            f"{self.pds_url}/xrpc/com.atproto.server.createSession",
            json={"identifier": self.handle, "password": self.app_password},
        )
        raise_for_platform_response(session_response)
        session = session_response.json()

        record_response = await client.post(
            f"{self.pds_url}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {session['accessJwt']}"},
            json={
                "repo": session["did"],
                "collection": "app.bsky.feed.post",
                "record": {
                    "$type": "app.bsky.feed.post",
                    "text": message,
                    "createdAt": now_utc().isoformat().replace("+00:00", "Z"),
                },
            },
        )
        raise_for_platform_response(record_response)
        uri = record_response.json()["uri"]
        rkey = uri.rsplit("/", 1)[-1]
        return PublishedPost(
            posted_url=f"https://bsky.app/profile/{self.handle}/post/{rkey}",
            public_access=True,
            posted_at=now_utc(),
        )
