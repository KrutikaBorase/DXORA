import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.schemas import GeminiFeedback, PlatformResult
from app.services.gemini_service import generate_gemini_feedback


MESSAGE = "Visit https://example.com"


@pytest.mark.asyncio
async def test_gemini_returns_feedback_without_changing_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "test-key"
        body = json.loads(request.content)
        assert body["contents"][0]["parts"][0]["text"] == MESSAGE
        return httpx.Response(
            200,
            json={
                "candidates": [{
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": "Clear message. "}, {"text": "CTA is present."}]},
                }]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await generate_gemini_feedback(
            MESSAGE, Settings(_env_file=None, gemini_api_key="test-key"), client
        )
    assert result.status == "success"
    assert result.feedback == "Clear message. CTA is present."
    assert result.error is None


@pytest.mark.asyncio
async def test_missing_gemini_key_does_not_make_a_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Gemini must not be called without a key")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await generate_gemini_feedback(
            MESSAGE, Settings(_env_file=None, gemini_api_key=""), client
        )
    assert result.status == "not_configured"
    assert result.error == "GEMINI_API_KEY is not configured"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        ("unauthorized", "Gemini API returned HTTP 401"),
        ("timeout", "Gemini request failed: ReadTimeout"),
        ("bad_json", "Gemini returned an invalid response"),
        ("blocked", "Gemini returned no feedback"),
        ("incomplete", "Gemini response incomplete: SAFETY"),
    ],
)
async def test_gemini_failures_are_reported_without_secrets(
    failure: str, expected_error: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "unauthorized":
            return httpx.Response(401, text="test-key")
        if failure == "timeout":
            raise httpx.ReadTimeout("test-key", request=request)
        if failure == "bad_json":
            return httpx.Response(200, text="invalid JSON")
        if failure == "blocked":
            return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})
        return httpx.Response(200, json={"candidates": [{"finishReason": "SAFETY"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await generate_gemini_feedback(
            MESSAGE, Settings(_env_file=None, gemini_api_key="test-key"), client
        )
    assert result.status == "failed"
    assert result.error == expected_error
    assert "test-key" not in result.error


def test_endpoint_isolates_gemini_failure_from_posting(monkeypatch) -> None:
    started = asyncio.Event()
    entered: list[str] = []

    async def publishing(message, settings, client):
        assert message == MESSAGE
        entered.append("posting")
        if len(entered) == 2:
            started.set()
        await asyncio.wait_for(started.wait(), timeout=2)
        return [PlatformResult(platform="Example", status="success")]

    async def feedback(message, settings, client):
        assert message == MESSAGE
        entered.append("gemini")
        if len(entered) == 2:
            started.set()
        await asyncio.wait_for(started.wait(), timeout=2)
        return GeminiFeedback(status="failed", error="Gemini unavailable")

    monkeypatch.setattr("app.main.publish_to_all", publishing)
    monkeypatch.setattr("app.main.generate_gemini_feedback", feedback)
    with TestClient(app) as client:
        response = client.post("/posting", json={"message": MESSAGE})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["results"][0]["status"] == "success"
    assert body["gemini"] == {
        "status": "failed",
        "feedback": None,
        "error": "Gemini unavailable",
    }
