from datetime import date as date_type
from datetime import time as time_type
from typing import Literal

import re

from pydantic import BaseModel, Field, HttpUrl, TypeAdapter, field_validator


URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


class PostingRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=200)

    @field_validator("message")
    @classmethod
    def validate_single_cta_link(cls, value: str) -> str:
        links = URL_PATTERN.findall(value)
        if len(links) != 1:
            raise ValueError("message must contain exactly one CTA link")

        link = links[0].rstrip(".,!?;:)]}")
        try:
            HTTP_URL_ADAPTER.validate_python(link)
        except ValueError as error:
            raise ValueError("CTA link must be a valid HTTP or HTTPS URL") from error
        return value


class PlatformResult(BaseModel):
    platform: str
    status: Literal["success", "failed"]
    posted_url: str | None = None
    public_access: bool = False
    date: date_type | None = None
    time: time_type | None = None
    error: str | None = None


class PostingResponse(BaseModel):
    success: bool
    results: list[PlatformResult]
