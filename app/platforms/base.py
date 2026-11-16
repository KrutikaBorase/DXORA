from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx


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
