"""Tests for OpenRouter VLM requests."""

from __future__ import annotations

from typing import Any, cast

import pytest

from paperbanana.core.cost_tracker import BudgetExceededError, CostTracker
from paperbanana.providers.vlm.openrouter import OpenRouterVLM


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": "diagram plan"}}],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "cost": 0.037,
            },
        }


class _FakeClient:
    async def post(self, path: str, json: dict) -> _FakeResponse:
        assert path == "/chat/completions"
        return _FakeResponse()


class _MissingUsageResponse(_FakeResponse):
    def json(self) -> dict:
        return {"choices": [{"message": {"content": "diagram plan"}}]}


class _MissingUsageClient(_FakeClient):
    async def post(self, path: str, json: dict) -> _MissingUsageResponse:
        assert path == "/chat/completions"
        return _MissingUsageResponse()


class _MalformedUsageResponse(_FakeResponse):
    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": "diagram plan"}}],
            "usage": ["unexpected"],
        }


class _MalformedUsageClient(_FakeClient):
    async def post(self, path: str, json: dict) -> _MalformedUsageResponse:
        assert path == "/chat/completions"
        return _MalformedUsageResponse()


class _MalformedUsageAndContentResponse(_FakeResponse):
    def json(self) -> dict:
        return {"choices": [], "usage": ["unexpected"]}


class _MalformedUsageAndContentClient(_FakeClient):
    def __init__(self) -> None:
        self.calls = 0

    async def post(self, path: str, json: dict) -> _MalformedUsageAndContentResponse:
        assert path == "/chat/completions"
        self.calls += 1
        return _MalformedUsageAndContentResponse()


class _MalformedContentResponse(_FakeResponse):
    def json(self) -> dict:
        return {"choices": [], "usage": {"cost": 0.019}}


class _MalformedContentClient(_FakeClient):
    async def post(self, path: str, json: dict) -> _MalformedContentResponse:
        assert path == "/chat/completions"
        return _MalformedContentResponse()


@pytest.mark.asyncio
async def test_generate_records_openrouter_reported_cost() -> None:
    provider = OpenRouterVLM(api_key="test-key", model="anthropic/claude-opus-4.8")
    tracker = CostTracker(budget=1.00)
    provider.cost_tracker = tracker
    cast(Any, provider)._client = _FakeClient()

    result = await provider.generate("Plan a diagram")

    assert result == "diagram plan"
    assert tracker.total_cost == pytest.approx(0.037)
    assert tracker.pricing_complete is True
    assert tracker.is_over_budget is False


@pytest.mark.asyncio
async def test_generate_without_usage_records_unknown_cost_and_fails_closed() -> None:
    provider = OpenRouterVLM(api_key="test-key", model="anthropic/claude-opus-4.8")
    tracker = CostTracker(budget=1.00)
    provider.cost_tracker = tracker
    cast(Any, provider)._client = _MissingUsageClient()

    with pytest.raises(BudgetExceededError):
        await provider.generate("Plan a diagram")

    assert len(tracker.entries) == 1
    assert tracker.entries[0].pricing_known is False
    assert tracker.is_over_budget is True


@pytest.mark.asyncio
async def test_generate_with_non_mapping_usage_records_unknown_cost() -> None:
    provider = OpenRouterVLM(api_key="test-key", model="anthropic/claude-opus-4.8")
    tracker = CostTracker(budget=1.00)
    provider.cost_tracker = tracker
    cast(Any, provider)._client = _MalformedUsageClient()

    with pytest.raises(BudgetExceededError):
        await provider.generate("Plan a diagram")

    assert len(tracker.entries) == 1
    assert tracker.entries[0].pricing_known is False
    assert tracker.is_over_budget is True


@pytest.mark.asyncio
async def test_unknown_cost_stops_before_malformed_content_can_retry() -> None:
    provider = OpenRouterVLM(api_key="test-key", model="anthropic/claude-opus-4.8")
    tracker = CostTracker(budget=1.00)
    provider.cost_tracker = tracker
    client = _MalformedUsageAndContentClient()
    cast(Any, provider)._client = client

    with pytest.raises(BudgetExceededError):
        await provider.generate("Plan a diagram")

    assert client.calls == 1
    assert len(tracker.entries) == 1
    assert tracker.entries[0].pricing_known is False


@pytest.mark.asyncio
async def test_billed_response_is_recorded_once_when_content_parsing_fails() -> None:
    provider = OpenRouterVLM(api_key="test-key", model="anthropic/claude-opus-4.8")
    tracker = CostTracker(budget=1.00)
    provider.cost_tracker = tracker
    cast(Any, provider)._client = _MalformedContentClient()

    with pytest.raises(IndexError):
        await cast(Any, OpenRouterVLM.generate).__wrapped__(provider, "Plan a diagram")

    assert len(tracker.entries) == 1
    assert tracker.total_cost == pytest.approx(0.019)
