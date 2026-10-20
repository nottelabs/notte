"""`JevDecider` / `LlmDecider` / `default_decider`, offline (HTTP and LLM calls mocked)."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from notte_core.act import DeciderNotAvailableError, DecisionState, PageState, Question, WriteContext
from notte_core.act import resolve as act_resolve
from notte_core.act.errors import InvalidDecisionError
from notte_core.errors import LLMProviderError, UnsupportedResponseSchemaError
from notte_llm import act as llm_act
from notte_llm.act import DEFAULT_ACT_MODEL, DEFAULT_TEXT_MODEL, JevDecider, LlmDecider, LlmWriter, default_decider

STATE = DecisionState(page=PageState(url="https://a.test", title="A", text="I1[:]<input name='q'></input>"))
QUESTIONS = {
    "operation": Question(criteria={"CLICK": "click", "DONE": "done"}, instructions={"goal": "g", "rules": "r"}),
    "click_target": Question(criteria={"B1": {"element": "[B1] Go"}, "L1": {"element": "[L1] Help"}}),
}
ENV = [
    "TYPESAFE_API_KEY",
    "TYPESAFE_MODEL",
    "OPENROUTER_API_KEY",
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
    [('{"text": "Jane"}', "Jane"), ('{"text": null}', None), ('```json\n{"text": "{{email}}"}\n```', "{{email}}")],
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
@pytest.mark.parametrize("output", ['{"text": ""}', '{"text": "a", "extra": 1}', '{"text": 3}', "not json"])
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


def test_default_decider_llm_from_openrouter_or_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
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
    # the OpenRouter key does not apply to another endpoint
    monkeypatch.delenv("NOTTE_LLM_API_KEY")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    with pytest.raises(DeciderNotAvailableError):
        _ = default_decider()


def test_jev_decider_without_llm_key_has_no_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    decider = default_decider()
    assert isinstance(decider, JevDecider) and not isinstance(decider.writer, LlmWriter)


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
