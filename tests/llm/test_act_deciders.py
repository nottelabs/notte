"""`JevDecider` / `LlmDecider` / `default_decider`, offline (HTTP and LLM calls mocked)."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from notte_core.act import DeciderNotAvailableError, DecisionState, PageState, Question, WriteContext
from notte_core.act import resolve as act_resolve
from notte_core.act.errors import InvalidDecisionError
from notte_core.errors import ContentFilterError, InvalidAPIKeyError, LLMProviderError, UnsupportedResponseSchemaError
from notte_llm import act as llm_act
from notte_llm.act import DEFAULT_ACT_MODEL, DEFAULT_TEXT_MODEL, JevDecider, LlmDecider, LlmWriter, default_decider
from pydantic import JsonValue

STATE = DecisionState(page=PageState(url="https://a.test", title="A", text="I1[:]<input name='q'></input>"))
QUESTIONS = {
    "operation": Question(criteria={"CLICK": "click", "DONE": "done"}, instructions={"goal": "g", "rules": "r"}),
    "click_target": Question(criteria={"B1": {"element": "[B1] Go"}, "L1": {"element": "[L1] Help"}}),
}
ENV = [
    "TYPESAFE_API_KEY",
    "TYPESAFE_MODEL",
    "OPENROUTER_API_KEY",
    "TYPESAFE_BASE_URL",
    "NOTTE_ACT_DECIDER",
    "NOTTE_LLM_API_KEY",
    "NOTTE_LLM_BASE_URL",
    "NOTTE_ACT_MODEL",
    "NOTTE_LLM_MODEL",
    "NOTTE_ACT_TEXT_MODEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


def _response(status: int, body: dict[str, Any] | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.is_success = 200 <= status < 300
    response.json.return_value = body or {}
    response.text = json.dumps(body or {})
    return response


@pytest.mark.asyncio
async def test_jev_decider_posts_the_questions_and_retries_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_act.time, "sleep", lambda _: None)
    decider = JevDecider(api_key="test-key", base_url="https://typesafe.test/")
    body = {
        "model": "jev-1.0",
        "answers": {
            "operation": {"choice": "CLICK", "probabilities": {"CLICK": 0.8, "DONE": 0.2}, "confidence": 0.8},
            "click_target": {"choice": "B1", "probabilities": {"B1": 0.7, "L1": 0.3}, "confidence": 0.7},
            "broken": {"unexpected": True},
        },
        "usage": {"tokens": 10},
    }
    post = MagicMock(side_effect=[_response(429), _response(200, body)])
    monkeypatch.setattr(decider._http, "post", post)  # pyright: ignore[reportPrivateUsage]

    answers = await decider.choose(STATE, QUESTIONS)

    assert post.call_count == 2
    url = post.call_args.args[0]
    sent = post.call_args.kwargs["json"]
    assert url == "https://typesafe.test/v1/systemone"
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer test-key"}
    assert sent["model"] == "jev-latest"
    assert set(sent["questions"]) == {"operation", "click_target"}
    assert sent["questions"]["operation"] == {
        "type": "choice",
        "criteria": {"CLICK": "click", "DONE": "done"},
        "instructions": {"goal": "g", "rules": "r"},
    }
    assert sent["state"]["page"]["url"] == "https://a.test"
    assert set(answers.answers) == {"operation", "click_target"}
    assert answers.model == "jev-1.0" and answers.usage == {"tokens": 10}


@pytest.mark.asyncio
async def test_jev_decider_http_error_executes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    decider = JevDecider(api_key="k")
    monkeypatch.setattr(decider._http, "post", MagicMock(return_value=_response(401)))  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(LLMProviderError, match="HTTP 401"):
        _ = await decider.choose(STATE, QUESTIONS)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["typesafe", "openrouter"])
@pytest.mark.parametrize("malformed", [None, [], ["operation"], "", "not-an-object", 1, False])
async def test_jev_rejects_non_object_answers_with_provider_error(
    monkeypatch: pytest.MonkeyPatch, route: llm_act.JevRoute, malformed: JsonValue
) -> None:
    decider = JevDecider(route=route, api_key="test-key")
    post = MagicMock(return_value=_response(200, {"answers": malformed}))
    monkeypatch.setattr(decider._http, "post", post)  # pyright: ignore[reportPrivateUsage]
    try:
        with pytest.raises(LLMProviderError, match="'answers' that is not a JSON object") as exc:
            await decider.choose(STATE, QUESTIONS)
        assert exc.value.should_retry_later is True
        assert decider.provider in exc.value.dev_message
        assert "test-key" not in exc.value.dev_message
        assert post.call_count == 1
    finally:
        decider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["typesafe", "openrouter"])
@pytest.mark.parametrize("malformed", [None, [], ["tokens"], "", "not-an-object", 1, False])
async def test_jev_keeps_valid_answers_when_usage_is_not_an_object(
    monkeypatch: pytest.MonkeyPatch, route: llm_act.JevRoute, malformed: JsonValue
) -> None:
    decider = JevDecider(route=route, api_key="test-key")
    post = MagicMock(
        return_value=_response(
            200,
            {
                "answers": {"operation": {"choice": "DONE", "probabilities": {"DONE": 1.0}, "confidence": 1.0}},
                "model": "selected-model",
                "usage": malformed,
            },
        )
    )
    monkeypatch.setattr(decider._http, "post", post)  # pyright: ignore[reportPrivateUsage]
    try:
        result = await decider.choose(STATE, QUESTIONS)
        assert result.answers["operation"].choice == "DONE"
        assert result.model == "selected-model"
        assert result.usage == {}
        assert post.call_count == 1
    finally:
        decider.close()


def test_jev_decider_closes_its_http_client() -> None:
    decider = JevDecider(api_key="k")
    decider.close()
    assert decider._http.is_closed  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_jev_decider_without_writer_explains_how_to_type(monkeypatch: pytest.MonkeyPatch) -> None:
    decider = JevDecider(api_key="k")
    with pytest.raises(DeciderNotAvailableError, match="text model"):
        _ = await decider.write(WriteContext(goal="g", field={}, page={}))


def _fake_complete(outputs: list[str], calls: list[dict[str, Any]]):  # pyright: ignore[reportUnknownParameterType]
    async def fake(model: str, messages: list[dict[str, Any]], response_format: dict[str, Any], max_tokens: int):  # pyright: ignore[reportUnusedParameter]
        calls.append({"model": model, "messages": messages, "response_format": response_format})
        return outputs.pop(0), {"total_tokens": 1}

    return fake


@pytest.mark.asyncio
async def test_llm_decider_uses_enum_schema_and_synthesizes_probabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    output = {"operation": {"choice": "CLICK", "confidence": 0.7}, "click_target": {"choice": "L1", "confidence": 3}}
    monkeypatch.setattr(llm_act, "_complete", _fake_complete([json.dumps(output)], calls))

    answers = await LlmDecider("some/model").choose(STATE, QUESTIONS)

    schema = calls[0]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["click_target"]["properties"]["choice"]["enum"] == ["B1", "L1"]
    assert schema["required"] == ["operation", "click_target"]
    assert answers.answers["operation"].probabilities == {"CLICK": 1.0, "DONE": 0.0}
    assert answers.answers["operation"].confidence == 0.7
    # clamped to [0, 1]
    assert answers.answers["click_target"].confidence == 1.0


@pytest.mark.asyncio
async def test_llm_decider_retries_once_when_a_question_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    incomplete = json.dumps({"operation": {"choice": "NOPE", "confidence": 1}})
    complete = json.dumps({"operation": {"choice": "DONE"}, "click_target": {"choice": "B1", "confidence": 0.9}})
    monkeypatch.setattr(llm_act, "_complete", _fake_complete([incomplete, complete], calls))

    answers = await LlmDecider("m").choose(STATE, QUESTIONS)
    assert len(calls) == 2
    # the second call says what was missing
    assert calls[1]["messages"][-2] == {"role": "assistant", "content": incomplete}
    assert "operation" in calls[1]["messages"][-1]["content"]
    # missing confidence: 0.5
    assert answers.answers["operation"].choice == "DONE" and answers.answers["operation"].confidence == 0.5


@pytest.mark.asyncio
async def test_llm_decider_falls_back_to_json_object(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    good = json.dumps(
        {"operation": {"choice": "DONE", "confidence": 1}, "click_target": {"choice": "B1", "confidence": 1}}
    )

    async def fake(model: str, messages: list[dict[str, Any]], response_format: dict[str, Any], max_tokens: int):  # pyright: ignore[reportUnusedParameter]
        calls.append(response_format)
        if response_format["type"] == "json_schema":
            raise UnsupportedResponseSchemaError(model, error_msg="schema too large")
        return good, {}

    monkeypatch.setattr(llm_act, "_complete", fake)
    answers = await LlmDecider("m").choose(STATE, QUESTIONS)
    assert [c["type"] for c in calls] == ["json_schema", "json_object"]
    assert answers.answers["click_target"].choice == "B1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ('{"text": "Jane"}', "Jane"),
        ('{"text": null}', None),
        # clearing the field
        ('{"text": ""}', ""),
        ('```json\n{"text": "{{email}}"}\n```', "{{email}}"),
    ],
)
async def test_writer_returns_exactly_the_text(
    monkeypatch: pytest.MonkeyPatch, output: str, expected: str | None
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(llm_act, "_complete", _fake_complete([output], calls))
    context = WriteContext(goal="g", field={"label": "Email"}, page={}, variables=["email"])
    assert await LlmWriter("m").write(context) == expected
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "{{name}}" in calls[0]["messages"][0]["content"]
    assert json.loads(calls[0]["messages"][1]["content"])["variables"] == ["email"]


@pytest.mark.asyncio
@pytest.mark.parametrize("output", ['{"text": "  "}', '{"text": "a", "extra": 1}', '{"text": 3}', "not json"])
async def test_writer_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch, output: str) -> None:
    monkeypatch.setattr(llm_act, "_complete", _fake_complete([output], []))
    with pytest.raises(InvalidDecisionError):
        _ = await LlmWriter("m").write(WriteContext(goal="g", field={}, page={}))


def test_default_decider_prefers_typesafe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    decider = default_decider()
    assert isinstance(decider, JevDecider)
    assert isinstance(decider.writer, LlmWriter) and decider.writer.model == DEFAULT_TEXT_MODEL


@pytest.mark.asyncio
async def test_default_jev_writes_when_the_endpoint_key_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setattr(llm_act, "_complete", _fake_complete(['{"text": "Hello"}'], []))
    decider = default_decider()
    assert isinstance(decider, JevDecider) and decider.route == "openrouter"
    try:
        assert await decider.write(WriteContext(goal="Say hello", field={}, page={})) == "Hello"
    finally:
        decider.close()


def test_default_decider_llm_from_openrouter_or_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    # with an OpenRouter key, the LLM decider is opt-in (Jev is the default)
    monkeypatch.setenv("NOTTE_ACT_DECIDER", "llm")
    decider = default_decider()
    assert isinstance(decider, LlmDecider) and decider.model == DEFAULT_ACT_MODEL
    assert decider.writer.model == DEFAULT_TEXT_MODEL

    monkeypatch.setenv("NOTTE_LLM_MODEL", "google/gemini-3.5-flash")
    assert isinstance(d := default_decider(), LlmDecider) and d.model == "google/gemini-3.5-flash"
    monkeypatch.setenv("NOTTE_ACT_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("NOTTE_ACT_TEXT_MODEL", "openai/gpt-4o-mini")
    d = default_decider()
    assert isinstance(d, LlmDecider) and d.model == "openai/gpt-4o" and d.writer.model == "openai/gpt-4o-mini"


def test_default_decider_on_another_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", "https://llm.test/v1")
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "k")
    # a custom endpoint has no default model
    with pytest.raises(DeciderNotAvailableError):
        _ = default_decider()
    monkeypatch.setenv("NOTTE_LLM_MODEL", "local-model")
    d = default_decider()
    # off OpenRouter, the writer uses the decision model
    assert isinstance(d, LlmDecider) and d.model == "local-model" and d.writer.model == "local-model"
    # an OpenRouter key selects Jev through OpenRouter; the writer stays on the configured endpoint
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    jev = default_decider()
    assert isinstance(jev, JevDecider) and jev.route == "openrouter"
    assert isinstance(jev.writer, LlmWriter) and jev.writer.model == "local-model" and jev.writer.fallback_model is None
    # without an endpoint key, Jev has no writer: the OpenRouter key is never sent to another endpoint
    monkeypatch.delenv("NOTTE_LLM_API_KEY")
    jev = default_decider()
    assert isinstance(jev, JevDecider) and not isinstance(jev.writer, LlmWriter)


def test_jev_decider_without_llm_key_has_no_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    decider = default_decider()
    assert isinstance(decider, JevDecider) and not isinstance(decider.writer, LlmWriter)


@pytest.mark.parametrize("choice", ["auto", "jev"])
@pytest.mark.parametrize("route", ["typesafe", "openrouter"])
@pytest.mark.parametrize("writer_key", [None, "writer-test-key"])
def test_jev_selection_does_not_require_a_configured_field_writer(
    monkeypatch: pytest.MonkeyPatch, choice: str, route: str, writer_key: str | None
) -> None:
    monkeypatch.setenv("NOTTE_ACT_DECIDER", choice)
    monkeypatch.setenv("TYPESAFE_API_KEY" if route == "typesafe" else "OPENROUTER_API_KEY", "decision-test-key")
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", "https://llm.test/v1")
    if writer_key is not None:
        monkeypatch.setenv("NOTTE_LLM_API_KEY", writer_key)
    decider = default_decider()
    assert isinstance(decider, JevDecider) and decider.route == route
    assert not isinstance(decider.writer, LlmWriter)


@pytest.mark.asyncio
async def test_llm_requests_disable_reasoning_and_fallback_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_complete` goes through `LLMEngine`: OpenRouter reasoning off, no fallback models, bounded tokens."""
    import httpx

    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        if len(sent) == 1:
            return httpx.Response(400, json={"error": {"message": "Reasoning is mandatory for this endpoint"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"text": "x"}'}}], "usage": {"n": 1}})

    real_engine = llm_act.LLMEngine
    monkeypatch.setattr(
        llm_act, "LLMEngine", lambda **kwargs: real_engine(transport=httpx.MockTransport(handler), **kwargs)
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(llm_act, "_REASONING_REQUIRED", set())
    content, usage = await llm_act._complete("vendor/model", [], {"type": "json_object"}, max_tokens=99)  # pyright: ignore[reportPrivateUsage]

    assert content == '{"text": "x"}' and usage == {"n": 1}
    assert sent[0]["reasoning"] == {"enabled": False} and "models" not in sent[0]
    assert sent[0]["max_completion_tokens"] == 99 and sent[0]["model"] == "vendor/model"
    # a model that requires reasoning is retried with the lowest effort
    assert sent[1]["reasoning"] == {"effort": "low"}


def test_default_decider_not_configured() -> None:
    with pytest.raises(DeciderNotAvailableError, match="TYPESAFE_API_KEY"):
        _ = act_resolve.default_decider()


def test_default_decider_without_notte_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> None:
        raise ImportError(name)

    monkeypatch.setattr(act_resolve.importlib, "import_module", missing)
    with pytest.raises(DeciderNotAvailableError, match="notte\\[llm\\]"):
        _ = act_resolve.default_decider()


def _refusing(models: set[str], calls: list[str]):  # pyright: ignore[reportUnknownParameterType]
    async def fake(model: str, messages: list[dict[str, Any]], response_format: dict[str, Any], max_tokens: int):  # pyright: ignore[reportUnusedParameter]
        calls.append(model)
        if model in models:
            raise ContentFilterError(model, "refused")
        return '{"text": "Ada Lovelace"}', {}

    return fake


CONTEXT = WriteContext(goal="search for Ada Lovelace", field={"label": "Search Wikipedia"}, page={})


@pytest.mark.asyncio
async def test_writer_asks_the_fallback_model_after_a_content_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(llm_act, "_complete", _refusing({"writer"}, calls))
    assert await LlmWriter("writer", fallback_model="decider").write(CONTEXT) == "Ada Lovelace"
    assert calls == ["writer", "decider"]


@pytest.mark.asyncio
async def test_writer_fails_clearly_when_both_models_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(llm_act, "_complete", _refusing({"writer", "decider"}, calls))
    with pytest.raises(ContentFilterError, match="Search Wikipedia") as exc:
        _ = await LlmWriter("writer", fallback_model="decider").write(CONTEXT)
    assert not isinstance(exc.value, InvalidAPIKeyError)
    assert "writer" in exc.value.model and "decider" in exc.value.model
    assert calls == ["writer", "decider"]


@pytest.mark.asyncio
async def test_writer_without_fallback_reraises_the_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(llm_act, "_complete", _refusing({"m"}, calls))
    # a fallback equal to the model is no fallback
    with pytest.raises(ContentFilterError):
        _ = await LlmWriter("m", fallback_model="m").write(CONTEXT)
    assert calls == ["m"]


@pytest.mark.asyncio
async def test_other_writer_errors_do_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake(model: str, messages: list[dict[str, Any]], response_format: dict[str, Any], max_tokens: int):  # pyright: ignore[reportUnusedParameter]
        calls.append(model)
        raise InvalidAPIKeyError(provider=model)

    monkeypatch.setattr(llm_act, "_complete", fake)
    with pytest.raises(InvalidAPIKeyError):
        _ = await LlmWriter("writer", fallback_model="decider").write(CONTEXT)
    assert calls == ["writer"]


def test_default_writers_fall_back_to_the_decision_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("NOTTE_ACT_DECIDER", "llm")
    llm = default_decider()
    assert isinstance(llm, LlmDecider) and llm.writer.fallback_model == DEFAULT_ACT_MODEL
    monkeypatch.delenv("NOTTE_ACT_DECIDER")
    for typesafe in (False, True):
        if typesafe:
            monkeypatch.setenv("TYPESAFE_API_KEY", "k")
        jev = default_decider()
        assert isinstance(jev, JevDecider) and isinstance(jev.writer, LlmWriter)
        # Jev cannot write: the fallback is a text model
        assert jev.writer.model == DEFAULT_TEXT_MODEL and jev.writer.fallback_model == DEFAULT_ACT_MODEL


OPENROUTER_DECISION = {
    "model": "typesafe/jev-1.14-20261014",
    "answers": {
        "operation": {
            "type": "choice",
            "choice": "CLICK",
            "probabilities": {"CLICK": 0.9, "DONE": 0.1},
            "confidence": 0.9,
        },
        "click_target": {
            "type": "choice",
            "choice": "B1",
            "probabilities": {"B1": 0.99, "L1": 0.01},
            "confidence": 0.99,
        },
    },
    "usage": {"input_tokens": 432, "output_tokens": 49, "cost": 1.8e-05},
    "id": "gen-dec-1",
    "provider": "TypeSafe",
}


@pytest.mark.asyncio
async def test_jev_through_openrouter_posts_to_the_decisions_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    decider = JevDecider()
    assert decider.route == "openrouter"
    post = MagicMock(return_value=_response(200, OPENROUTER_DECISION))
    monkeypatch.setattr(decider._http, "post", post)  # pyright: ignore[reportPrivateUsage]

    answers = await decider.choose(STATE, QUESTIONS)

    assert post.call_args.args[0] == "https://openrouter.ai/api/alpha/decisions"
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer or-key"}
    sent = post.call_args.kwargs["json"]
    assert sent["model"] == "~typesafe/jev-latest" and set(sent) == {"model", "state", "questions"}
    assert answers.answers["click_target"].choice == "B1" and answers.answers["click_target"].confidence == 0.99
    assert answers.model == "typesafe/jev-1.14-20261014" and answers.usage["cost"] == 1.8e-05


def test_jev_route_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(DeciderNotAvailableError, match="OPENROUTER_API_KEY"):
        _ = JevDecider()
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    assert JevDecider().url == "https://openrouter.ai/api/alpha/decisions"
    # an OpenRouter key given as NOTTE_LLM_API_KEY at the default endpoint
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "llm-key")
    assert JevDecider().route == "openrouter"
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-key")
    direct = JevDecider()
    assert (
        direct.route == "typesafe"
        and direct.url == "https://api.typesafe.ai/v1/systemone"
        and direct.model == "jev-latest"
    )
    # overrides: model, base URL, explicit route and key
    monkeypatch.setenv("TYPESAFE_MODEL", "jev-1.14")
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://typesafe.test/")
    assert JevDecider().url == "https://typesafe.test/v1/systemone" and JevDecider().model == "jev-1.14"
    routed = JevDecider(route="openrouter", api_key="explicit", base_url="https://proxy.test/api/")
    assert routed.url == "https://proxy.test/api/alpha/decisions" and routed._api_key == "explicit"  # pyright: ignore[reportPrivateUsage]
    assert routed.model == "jev-1.14"
    monkeypatch.delenv("NOTTE_LLM_API_KEY")
    with pytest.raises(DeciderNotAvailableError, match="OPENROUTER_API_KEY"):
        _ = JevDecider(route="openrouter")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "match", "retry_later"),
    [
        (400, {"error": {"message": "state: Required"}}, "HTTP 400: state: Required", False),
        (401, {"error": {"message": "No auth credentials found"}}, "HTTP 401", False),
        (
            200,
            {"error": {"message": "Upstream error from TypeSafe", "code": 502}},
            "Upstream error from TypeSafe",
            True,
        ),
    ],
)
async def test_jev_errors_name_the_endpoint(
    monkeypatch: pytest.MonkeyPatch, status: int, body: dict[str, Any], match: str, retry_later: bool
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    decider = JevDecider()
    monkeypatch.setattr(decider._http, "post", MagicMock(return_value=_response(status, body)))  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(LLMProviderError, match=match) as exc:
        _ = await decider.choose(STATE, QUESTIONS)
    assert "https://openrouter.ai/api/alpha/decisions" in exc.value.dev_message
    assert "OpenRouter" in exc.value.user_message and "or-key" not in exc.value.dev_message
    assert exc.value.should_retry_later is retry_later


@pytest.mark.asyncio
async def test_jev_retries_openrouter_upstream_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_act.time, "sleep", lambda _: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    decider = JevDecider()
    post = MagicMock(side_effect=[_response(502), _response(200, OPENROUTER_DECISION)])
    monkeypatch.setattr(decider._http, "post", post)  # pyright: ignore[reportPrivateUsage]
    assert set((await decider.choose(STATE, QUESTIONS)).answers) == {"operation", "click_target"}
    assert post.call_count == 2


def test_resolution_order(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. TypeSafe directly
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or")
    assert isinstance(d := default_decider(), JevDecider) and d.route == "typesafe"
    # 2. Jev through OpenRouter
    monkeypatch.delenv("TYPESAFE_API_KEY")
    assert isinstance(d := default_decider(), JevDecider) and d.route == "openrouter"
    # NOTTE_ACT_DECIDER=llm keeps the LLM decider available
    monkeypatch.setenv("NOTTE_ACT_DECIDER", "llm")
    assert isinstance(default_decider(), LlmDecider)
    monkeypatch.setenv("NOTTE_ACT_DECIDER", "nope")
    with pytest.raises(DeciderNotAvailableError, match="NOTTE_ACT_DECIDER"):
        _ = default_decider()
    # 3. another endpoint without an OpenRouter key: the LLM decider
    monkeypatch.delenv("NOTTE_ACT_DECIDER")
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", "https://llm.test/v1")
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "k")
    monkeypatch.setenv("NOTTE_LLM_MODEL", "local-model")
    assert isinstance(d := default_decider(), LlmDecider) and d.model == "local-model"
    # NOTTE_ACT_DECIDER=jev refuses to fall back to an LLM
    monkeypatch.setenv("NOTTE_ACT_DECIDER", "jev")
    with pytest.raises(DeciderNotAvailableError, match="NOTTE_ACT_DECIDER=jev"):
        _ = default_decider()


@pytest.mark.parametrize("base_url", ["", "https://openrouter.ai/api/v1/"])
def test_an_empty_or_openrouter_base_url_is_openrouter(monkeypatch: pytest.MonkeyPatch, base_url: str) -> None:
    from notte_llm.config import LlmSettings

    monkeypatch.setenv("NOTTE_LLM_BASE_URL", base_url)
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "llm-key")
    # the writer's endpoint and Jev's route agree that this is OpenRouter
    assert LlmSettings.from_env().is_openrouter
    assert JevDecider().route == "openrouter"
    monkeypatch.setenv("NOTTE_ACT_DECIDER", "jev")
    decider = default_decider()
    assert isinstance(decider, JevDecider) and decider._api_key == "llm-key"  # pyright: ignore[reportPrivateUsage]
    assert isinstance(decider.writer, LlmWriter) and decider.writer.model == DEFAULT_TEXT_MODEL


def test_default_writer_is_mercury_3_on_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    decider = default_decider()
    assert isinstance(decider, JevDecider) and isinstance(decider.writer, LlmWriter)
    assert decider.writer.model == "inception/mercury-3"


@pytest.mark.asyncio
async def test_an_empty_model_reply_is_no_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    real_engine = llm_act.LLMEngine
    monkeypatch.setattr(
        llm_act, "LLMEngine", lambda **kwargs: real_engine(transport=httpx.MockTransport(handler), **kwargs)
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    content, _ = await llm_act._complete("vendor/model", [], {"type": "json_object"}, max_tokens=10)  # pyright: ignore[reportPrivateUsage]
    assert content == ""
    # the decider gets no answers (act() then reports an invalid decision); the writer an invalid value
    assert (await LlmDecider("vendor/model").choose(STATE, QUESTIONS)).answers == {}
    with pytest.raises(InvalidDecisionError):
        _ = await LlmWriter("vendor/model").write(WriteContext(goal="g", field={}, page={}))


@pytest.mark.parametrize(
    ("variables", "match"),
    [
        ({"NOTTE_LLM_BASE_URL": "https://llm.test/v1", "NOTTE_LLM_API_KEY": "k"}, "NOTTE_LLM_MODEL"),
        ({"NOTTE_LLM_BASE_URL": "ftp://llm.test", "NOTTE_LLM_API_KEY": "k"}, "HTTP"),
    ],
)
def test_invalid_llm_settings_say_what_is_wrong(
    monkeypatch: pytest.MonkeyPatch, variables: dict[str, str], match: str
) -> None:
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(DeciderNotAvailableError, match=match) as exc:
        _ = default_decider()
    # not a missing key: the key is there
    assert "invalid" in str(exc.value)
