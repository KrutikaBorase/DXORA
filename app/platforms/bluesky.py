import logging

import httpx

from app.config import Settings
from app.links import extract_cta_link
from app.platforms.base import (
    PlatformError,
    PublishedPost,
    fetch_public_json,
    now_utc,
    raise_for_platform_response,
)

logger = logging.getLogger(__name__)


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

        link = extract_cta_link(message)
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
                    "facets": [
                        {
                            "index": {
                                "byteStart": len(message[:link.start].encode("utf-8")),
                                "byteEnd": len(message[:link.end].encode("utf-8")),
                            },
                            "features": [
                                {"$type": "app.bsky.richtext.facet#link", "uri": link.url}
                            ],
                        }
                    ],
                    "createdAt": now_utc().isoformat().replace("+00:00", "Z"),
                },
            },
        )
        raise_for_platform_response(record_response)
        uri = record_response.json()["uri"]
        rkey = uri.rsplit("/", 1)[-1]
        public_post = await fetch_public_json(
            client,
            self.name,
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread",
            params={"uri": uri},
        )
        thread = public_post.get("thread") if public_post else None
        post = thread.get("post") if isinstance(thread, dict) else None
        public_access = isinstance(post, dict) and post.get("uri") == uri
        if not public_access:
            logger.warning("%s post visibility could not be confirmed", self.name)
        return PublishedPost(
            posted_url=f"https://bsky.app/profile/{self.handle}/post/{rkey}",
            public_access=public_access,
            posted_at=now_utc(),
        )
