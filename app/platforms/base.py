import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class PlatformError(Exception):
    """An expected platform or configuration failure."""


@dataclass(frozen=True)
class PublishedPost:
    posted_url: str | None
    public_access: bool
    posted_at: datetime


class Platform(Protocol):
    name: str

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        ...


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def raise_for_platform_response(response: httpx.Response) -> None:
    if response.is_error:
        detail = response.text[:300] or response.reason_phrase
        raise PlatformError(f"{response.status_code}: {detail}")


async def fetch_public_json(
    client: httpx.AsyncClient,
    platform: str,
    url: str,
    params: dict[str, str] | None = None,
) -> dict | None:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        return payload
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(
            "%s public access check failed: %s", platform, type(error).__name__
        )
        return None
