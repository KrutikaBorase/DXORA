import asyncio

import httpx
from fastapi import FastAPI

from app.config import get_settings
from app.schemas import PostingRequest, PostingResponse
from app.services.gemini_service import generate_gemini_feedback
from app.services.posting_service import publish_to_all

app = FastAPI(
    title="Automated Multi-Platform Posting API",
    description="Publish a short message to configured social platforms.",
    version="1.0.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/posting", response_model=PostingResponse)
async def create_post(request: PostingRequest) -> PostingResponse:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20.0) as client:
        results, gemini = await asyncio.gather(
            publish_to_all(request.message, settings, client),
            generate_gemini_feedback(request.message, settings, client),
        )
    return PostingResponse(
        success=any(result.status == "success" for result in results),
        results=results,
        gemini=gemini,
    )
