import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.explain import Explainer
from app.services.scoring import rank


def provider(*, result=None, error=None):
    create = AsyncMock(return_value=result, side_effect=error)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=AsyncMock())


def response(payload, finish_reason="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish_reason,
        message=SimpleNamespace(content=json.dumps(payload)))])


@pytest.mark.asyncio
async def test_openai_to_nvidia_fallback_preserves_ranking(store, config):
    data = store.snapshot()
    employee = data.employees["E0001"]
    items = rank(data, employee)[0]
    before = [(item.event_id, item.score, item.factors.model_dump()) for item in items]
    texts = {item.event_id: f"Explanation for {item.event_id}" for item in items}
    failed = provider(error=ConnectionError("offline"))
    working = provider(result=response({"explanations": texts}))
    explainer = Explainer(config)
    explainer.providers = [("openai", "gpt-4o-mini", failed), ("nvidia", "meta/llama-3.1-70b-instruct", working)]
    assert await explainer.explain(data, employee, items) is True
    assert all(item.explanation_source == "nvidia" and item.explanation == texts[item.event_id] for item in items)
    assert before == [(item.event_id, item.score, item.factors.model_dump()) for item in items]
    assert working.chat.completions.create.call_args.kwargs["temperature"] == 0
    assert failed.chat.completions.create.await_count == 1
    await explainer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["failure", "empty", "wrong_ids", "truncated", "invalid_json", "timeout"])
async def test_invalid_or_unavailable_providers_always_use_template(store, config, mode):
    data = store.snapshot()
    employee = data.employees["E0001"]
    items = rank(data, employee)[0]
    texts = {item.event_id: "" if mode == "empty" else "text" for item in items}
    if mode == "wrong_ids":
        texts = {"INVENTED_EVENT": "text"}
    result = response({"explanations": texts}, "length" if mode == "truncated" else "stop")
    if mode == "invalid_json":
        result.choices[0].message.content = "not JSON"
    first = provider(result=result, error=RuntimeError("offline") if mode == "failure" else None)
    if mode == "timeout":
        async def slow(**kwargs):
            await asyncio.sleep(10)
        first.chat.completions.create = slow
    second = provider(error=ConnectionError("also offline"))
    explainer = Explainer(config)
    explainer.timeout = 0.01
    explainer.providers = [("openai", "gpt-4o-mini", first), ("nvidia", "meta/llama-3.1-70b-instruct", second)]
    assert await explainer.explain(data, employee, items) is False
    assert all(item.explanation and item.explanation_source == "template" for item in items)
    assert second.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_no_key_and_empty_recommendations_need_no_network(store, config):
    explainer = Explainer(config)
    assert not explainer.available
    data = store.snapshot()
    assert await explainer.explain(data, data.employees["E0001"], []) is False


def test_clients_use_explicit_keys_timeouts_and_no_retries(config, monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.explain.AsyncOpenAI", lambda **kwargs: calls.append(kwargs) or provider())
    explainer = Explainer(config.model_copy(update={
        "OPENAI_API_KEY": config.OPENAI_API_KEY.__class__("test-openai"),
        "NVIDIA_API_KEY": config.NVIDIA_API_KEY.__class__("test-nvidia"),
    }))
    assert explainer.available and len(calls) == 2
    assert all(call["max_retries"] == 0 and call["timeout"] == 4 for call in calls)
    assert calls[1]["base_url"] == "https://integrate.api.nvidia.com/v1"
