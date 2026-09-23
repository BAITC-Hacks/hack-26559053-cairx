import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from openai import APIStatusError
import pytest

from app.services.explain import Explainer, explanation_context, template
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
    explanation = "This course develops skills needed for the next grade through its documented topics."
    failed = provider(error=ConnectionError("offline"))
    working = provider(result=response({"explanation": explanation}))
    explainer = Explainer(config)
    explainer.providers = [("openai", "gpt-4o-mini", failed), ("nvidia", "meta/llama-3.1-70b-instruct", working)]
    assert await explainer.explain(data, employee, items) is True
    assert all(item.explanation_source == "nvidia" and item.explanation == explanation for item in items)
    assert all(item.explanation_fallback_reason is None for item in items)
    assert before == [(item.event_id, item.score, item.factors.model_dump()) for item in items]
    assert working.chat.completions.create.call_args.kwargs["temperature"] == 0
    assert failed.chat.completions.create.await_count == len(items)
    await explainer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["failure", "empty", "wrong_fields", "truncated", "invalid_json", "timeout"])
async def test_invalid_or_unavailable_providers_always_use_template(store, config, mode):
    data = store.snapshot()
    employee = data.employees["E0001"]
    items = rank(data, employee)[0]
    payload = {"explanation": "" if mode == "empty" else "text"}
    if mode == "wrong_fields":
        payload = {"INVENTED_EVENT": "text"}
    result = response(payload, "length" if mode == "truncated" else "stop")
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
    assert second.chat.completions.create.await_count == len(items)
    assert all(item.explanation_fallback_reason == "provider_error" for item in items)


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
    assert all(call["max_retries"] == 0 and call["timeout"] == config.LLM_TIMEOUT_SECONDS for call in calls)
    assert calls[1]["base_url"] == "https://integrate.api.nvidia.com/v1"


def test_context_contains_actual_course_and_skill_descriptions_without_employee_identity(store):
    data = store.snapshot()
    employee = data.employees["E0001"]
    item = rank(data, employee)[0][0]
    context = explanation_context(data, employee, item)
    assert context["activity"]["description"] == data.events[item.event_id].description
    assert context["employee"]["current_grade"] == employee.grade
    assert context["employee"]["target_grade"] == "Middle"
    assert all(skill["description"] for skill in context["skills_to_develop"])
    gap = item.factors.gap_closure
    closes_gap = gap.current + gap.gain >= gap.required
    assert (context["skills_to_develop"][0]["expected_outcome"] == "closes_this_skill_gap") == closes_gap
    assert "current_level" not in context["skills_to_develop"][0]
    assert employee.employee_id not in json.dumps(context)
    assert employee.full_name not in json.dumps(context)


def test_template_explains_purpose_and_does_not_invent_history(store):
    data = store.snapshot()
    employee = data.employees["E0001"]
    item = rank(data, employee)[0][0]
    text = template(data, employee, item)
    assert employee.role in text and "Middle" in text
    assert data.events[item.event_id].description in text
    assert "В загруженной истории нет похожих активностей" in text
    assert "препятствует готовности" in text
    assert "остальных требований" in text


@pytest.mark.asyncio
async def test_openai_uses_structured_output_and_reuses_only_successful_explanations(store, config):
    data = store.snapshot()
    employee = data.employees["E0001"]
    fake = provider(result=response({"explanation": "Course-specific career advice based on its actual content."}))
    explainer = Explainer(config)
    explainer.providers = [("openai", "gpt-4o-mini", fake)]
    first = rank(data, employee)[0]
    assert await explainer.explain(data, employee, first)
    assert all(not item.explanation_cached for item in first)
    call = fake.chat.completions.create.call_args.kwargs
    assert call["response_format"]["json_schema"]["strict"] is True
    assert "factual_explanation" not in json.loads(call["messages"][1]["content"])
    second = rank(data, employee)[0]
    assert await explainer.explain(data, employee, second)
    assert fake.chat.completions.create.await_count == len(first)
    assert all(item.explanation_cached and item.explanation_source == "openai" for item in second)
    assert all(item.explanation_model == "gpt-4o-mini" for item in second)
    # Uploading new course content changes the prompt facts and must invalidate that card's cached text.
    event = data.events[first[0].event_id].model_dump(mode="json")
    event["description"] = "New course topics after a jury upload."
    store.merge({"events.json": json.dumps([event]).encode()})
    updated = store.snapshot()
    third = rank(updated, employee)[0]
    await explainer.explain(updated, employee, third)
    assert fake.chat.completions.create.await_count == len(first) + 1
    assert not third[0].explanation_cached


@pytest.mark.asyncio
async def test_timeout_is_reported_and_fallback_is_not_cached(store, config):
    data = store.snapshot()
    employee = data.employees["E0001"]
    fake = provider(error=TimeoutError())
    explainer = Explainer(config)
    explainer.providers = [("openai", "gpt-4o-mini", fake)]
    items = rank(data, employee)[0]
    assert not await explainer.explain(data, employee, items)
    assert all(item.explanation_fallback_reason == "timeout" for item in items)
    assert not explainer.cache
    fake.chat.completions.create.side_effect = None
    fake.chat.completions.create.return_value = response({"explanation": "The provider is available again."})
    assert await explainer.explain(data, employee, items)
    assert all(item.explanation_fallback_reason is None for item in items)


@pytest.mark.asyncio
async def test_cards_run_concurrently_and_providers_share_total_deadline(store, config):
    data = store.snapshot()
    employee = data.employees["E0001"]
    active = peak = 0

    async def slow(**kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(5)
        finally:
            active -= 1

    first = provider(error=slow)
    second = provider(error=slow)
    explainer = Explainer(config)
    explainer.timeout = 0.04
    explainer.total_timeout = 0.06
    explainer.providers = [("openai", "gpt-4o-mini", first), ("nvidia", "test-model", second)]
    items = rank(data, employee)[0]
    started = time.monotonic()
    assert not await explainer.explain(data, employee, items)
    assert time.monotonic() - started < 0.2
    assert peak == len(items)
    assert all(item.explanation_fallback_reason == "timeout" for item in items)
    assert active == 0


@pytest.mark.asyncio
async def test_no_credentials_are_reported_truthfully(store, config):
    data = store.snapshot()
    employee = data.employees["E0001"]
    items = rank(data, employee)[0]
    assert not await Explainer(config).explain(data, employee, items)
    assert all(item.explanation_source == "template" and item.explanation_fallback_reason == "not_configured" for item in items)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,reason", [(401, "authentication"), (403, "authentication"),
                                          (429, "rate_limit"), (500, "provider_error")])
async def test_provider_failure_class_is_visible_without_error_body(store, config, status, reason):
    data = store.snapshot()
    employee = data.employees["E0001"]
    api_response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
    fake = provider(error=APIStatusError("private diagnostic", response=api_response, body={"private": "details"}))
    explainer = Explainer(config)
    explainer.providers = [("openai", "gpt-4o-mini", fake)]
    items = rank(data, employee)[0]
    assert not await explainer.explain(data, employee, items)
    assert all(item.explanation_fallback_reason == reason for item in items)
    assert "private" not in json.dumps([item.model_dump() for item in items])


@pytest.mark.asyncio
async def test_mixed_provider_outcomes_keep_per_card_sources(store, config):
    data = store.snapshot()
    employee = data.employees["E0001"]
    fake = provider(error=[TimeoutError(), response({"explanation": "Actual LLM paragraph for the second card."})])
    explainer = Explainer(config)
    explainer.providers = [("openai", "gpt-4o-mini", fake)]
    items = rank(data, employee)[0]
    assert len(items) == 2
    assert await explainer.explain(data, employee, items)
    assert items[0].explanation_source == "template" and items[0].explanation_fallback_reason == "timeout"
    assert items[1].explanation_source == "openai" and items[1].explanation_fallback_reason is None


@pytest.mark.asyncio
async def test_numeric_history_changes_and_expiry_force_fresh_generation(store, config):
    data = store.snapshot()
    employee = data.employees["E0001"]
    fake = provider(result=response({"explanation": "Advice based on the current history."}))
    explainer = Explainer(config)
    explainer.providers = [("openai", "gpt-4o-mini", fake)]
    item = rank(data, employee)[0][0]
    item.factors.history_fit.similar_attended = 1
    await explainer.explain(data, employee, [item])
    item.factors.history_fit.similar_attended = 2  # same qualitative interpretation, different facts
    await explainer.explain(data, employee, [item])
    assert fake.chat.completions.create.await_count == 2
    assert not item.explanation_cached
    explainer.CACHE_TTL_SECONDS = 0
    await explainer.explain(data, employee, [item])
    assert fake.chat.completions.create.await_count == 3
    assert not item.explanation_cached
