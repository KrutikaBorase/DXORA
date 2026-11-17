from datetime import date as date_type
from datetime import time as time_type
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.links import extract_cta_link



class PostingRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=200)

    @field_validator("message")
    @classmethod
    def validate_single_cta_link(cls, value: str) -> str:
        extract_cta_link(value)
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
