"""Tests for OpenRouter image generation requests."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, cast

import pytest
from PIL import Image

from paperbanana.core.cost_tracker import BudgetExceededError, CostTracker
from paperbanana.providers.image_gen.openrouter_imagen import OpenRouterImageGen


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        image = Image.new("RGB", (1, 1), "white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return {
            "choices": [
                {
                    "message": {
                        "images": [{"image_url": {"url": f"data:image/png;base64,{encoded}"}}]
                    }
                }
            ],
            "usage": {"cost": 0.23},
        }


class _FakeClient:
    def __init__(self):
        self.last_payload: dict | None = None

    async def post(self, path: str, json: dict) -> _FakeResponse:
        assert path == "/chat/completions"
        self.last_payload = json
        return _FakeResponse(json)


class _MalformedUsageImageResponse(_FakeResponse):
    def json(self) -> dict:
        payload = super().json()
        payload["usage"] = ["unexpected"]
        return payload


class _MalformedUsageImageClient(_FakeClient):
    async def post(self, path: str, json: dict) -> _MalformedUsageImageResponse:
        assert path == "/chat/completions"
        self.last_payload = json
        return _MalformedUsageImageResponse(json)


class _MalformedUsageAndImageResponse(_FakeResponse):
    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": "no image returned"}}],
            "usage": ["unexpected"],
        }


class _MalformedUsageAndImageClient(_FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def post(self, path: str, json: dict) -> _MalformedUsageAndImageResponse:
        assert path == "/chat/completions"
        self.calls += 1
        self.last_payload = json
        return _MalformedUsageAndImageResponse(json)


class _MalformedImageResponse(_FakeResponse):
    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": "no image returned"}}],
            "usage": {"cost": 0.23},
        }


class _MalformedImageClient(_FakeClient):
    async def post(self, path: str, json: dict) -> _MalformedImageResponse:
        assert path == "/chat/completions"
        self.last_payload = json
        return _MalformedImageResponse(json)


@pytest.mark.asyncio
async def test_default_model_targets_stable_gemini_3_pro_image() -> None:
    provider = OpenRouterImageGen(api_key="test-key")

    assert cast(Any, provider)._model == "google/gemini-3-pro-image"


@pytest.mark.asyncio
async def test_generate_sends_openrouter_native_aspect_ratio() -> None:
    """OpenRouter image models receive the requested ratio in image_config."""
    provider = OpenRouterImageGen(api_key="test-key")
    client = _FakeClient()
    cast(Any, provider)._client = client

    image = await provider.generate(prompt="A system diagram", aspect_ratio="16:9")

    assert image.size == (1, 1)
    assert client.last_payload is not None
    assert client.last_payload["image_config"] == {"aspect_ratio": "16:9"}


@pytest.mark.asyncio
async def test_generate_records_openrouter_image_reported_cost() -> None:
    provider = OpenRouterImageGen(api_key="test-key", model="google/gemini-3-pro-image")
    tracker = CostTracker(budget=1.00)
    provider.cost_tracker = tracker
    cast(Any, provider)._client = _FakeClient()

    await provider.generate(prompt="A system diagram")

    assert tracker.total_cost == pytest.approx(0.23)
    assert tracker.pricing_complete is True
    assert tracker.is_over_budget is False


@pytest.mark.asyncio
async def test_generate_with_non_mapping_usage_records_unknown_image_cost() -> None:
    provider = OpenRouterImageGen(api_key="test-key", model="google/gemini-3-pro-image")
    tracker = CostTracker(budget=1.00)
    provider.cost_tracker = tracker
    cast(Any, provider)._client = _MalformedUsageImageClient()

    with pytest.raises(BudgetExceededError):
        await provider.generate(prompt="A system diagram")

    assert len(tracker.entries) == 1
    assert tracker.entries[0].pricing_known is False
    assert tracker.is_over_budget is True


@pytest.mark.asyncio
async def test_unknown_image_cost_stops_before_malformed_content_can_retry() -> None:
    provider = OpenRouterImageGen(api_key="test-key", model="google/gemini-3-pro-image")
    tracker = CostTracker(budget=1.00)
    provider.cost_tracker = tracker
    client = _MalformedUsageAndImageClient()
    cast(Any, provider)._client = client

    with pytest.raises(BudgetExceededError):
        await provider.generate(prompt="A system diagram")

    assert client.calls == 1
    assert len(tracker.entries) == 1
    assert tracker.entries[0].pricing_known is False


@pytest.mark.asyncio
async def test_billed_image_response_is_recorded_once_when_parsing_fails() -> None:
    provider = OpenRouterImageGen(api_key="test-key", model="google/gemini-3-pro-image")
    tracker = CostTracker(budget=1.00)
    provider.cost_tracker = tracker
    cast(Any, provider)._client = _MalformedImageClient()

    with pytest.raises(ValueError, match="did not contain image data"):
        await cast(Any, OpenRouterImageGen.generate).__wrapped__(
            provider, prompt="A system diagram"
        )

    assert len(tracker.entries) == 1
    assert tracker.total_cost == pytest.approx(0.23)
