import httpx

from app.config import Settings
from app.platforms.base import (
    PlatformError,
    PublishedPost,
    now_utc,
    raise_for_platform_response,
)


class RedditPlatform:
    name = "Reddit"

    def __init__(self, settings: Settings) -> None:
        self.client_id = settings.reddit_client_id
        self.client_secret = settings.reddit_client_secret
        self.username = settings.reddit_username
        self.password = settings.reddit_password
        self.subreddit = settings.reddit_subreddit
        self.user_agent = settings.reddit_user_agent

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        required = (
            self.client_id,
            self.client_secret,
            self.username,
            self.password,
            self.subreddit,
        )
        if not all(required):
            raise PlatformError(
                "Reddit credentials and REDDIT_SUBREDDIT are not fully configured"
            )

        token_response = await client.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(self.client_id, self.client_secret),
            data={
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
            },
            headers={"User-Agent": self.user_agent},
        )
        raise_for_platform_response(token_response)
        token = token_response.json().get("access_token")
        if not token:
            raise PlatformError("Reddit did not return an access token")

        post_response = await client.post(
            "https://oauth.reddit.com/api/submit",
            headers={
                "Authorization": f"bearer {token}",
                "User-Agent": self.user_agent,
            },
            data={
                "api_type": "json",
                "kind": "self",
                "sr": self.subreddit,
                "title": message[:300],
                "text": message,
            },
        )
        raise_for_platform_response(post_response)
        errors = post_response.json().get("json", {}).get("errors", [])
        if errors:
            raise PlatformError("; ".join(str(error) for error in errors))
        post_url = post_response.json().get("json", {}).get("data", {}).get("url")
        if not post_url:
            raise PlatformError("Reddit response did not include a post URL")
        return PublishedPost(
            posted_url=post_url,
            public_access=False,
            posted_at=now_utc(),
        )
