"""The RunAnywhere integration page's settings route `act()` to RunAnywhere, offline (HTTP mocked)."""

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from notte_core.act import WriteContext
from notte_llm import act as llm_act
from notte_llm.act import LlmDecider, LlmWriter, default_decider

ENV_SNIPPET = Path(__file__).resolve().parents[2] / "docs/src/testers/integrations/runanywhere/env.sh"
# top-level fields of RunAnywhere's `POST /v1/chat/completions` request schema (`additionalProperties: false`)
RUNANYWHERE_FIELDS = {
    "frequency_penalty",
    "max_completion_tokens",
    "max_tokens",
    "messages",
    "model",
    "n",
    "parallel_tool_calls",
    "presence_penalty",
    "reasoning_effort",
    "response_format",
    "seed",
    "stop",
    "store",
    "stream",
    "stream_options",
    "temperature",
    "tool_choice",
    "tools",
    "top_p",
    "user",
}


def _documented_env() -> dict[str, str]:
    return dict(re.findall(r"^export (\w+)=(\S+)$", ENV_SNIPPET.read_text(), flags=re.MULTILINE))


@pytest.fixture(autouse=True)
def documented_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for name in [
        "TYPESAFE_API_KEY",
        "OPENROUTER_API_KEY",
        "NOTTE_ACT_DECIDER",
        "NOTTE_ACT_MODEL",
        "NOTTE_ACT_TEXT_MODEL",
    ]:
        monkeypatch.delenv(name, raising=False)
    env = _documented_env()
    assert set(env) == {"NOTTE_LLM_BASE_URL", "NOTTE_LLM_API_KEY", "NOTTE_LLM_MODEL"}
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return env


def test_documented_settings_decide_and_write_on_runanywhere(
    monkeypatch: pytest.MonkeyPatch, documented_env: dict[str, str]
) -> None:
    model = documented_env["NOTTE_LLM_MODEL"]
    decider = default_decider()
    assert isinstance(decider, LlmDecider) and decider.model == model
    assert isinstance(decider.writer, LlmWriter) and decider.writer.model == model
    # with another decision key set, NOTTE_ACT_DECIDER=llm keeps decisions on RunAnywhere
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test-key")
    monkeypatch.setenv("NOTTE_ACT_DECIDER", "llm")
    assert isinstance(default_decider(), LlmDecider)


@pytest.mark.asyncio
async def test_requests_reach_runanywhere_with_accepted_fields(
    monkeypatch: pytest.MonkeyPatch, documented_env: dict[str, str]
) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"text": "Ada Lovelace"}'}}]})

    real_engine = llm_act.LLMEngine
    monkeypatch.setattr(
        llm_act, "LLMEngine", lambda **kwargs: real_engine(transport=httpx.MockTransport(handler), **kwargs)
    )
    writer = LlmWriter(documented_env["NOTTE_LLM_MODEL"])
    context = WriteContext(goal="type Ada Lovelace in the search box", field={"label": "Search"}, page={})
    assert await writer.write(context) == "Ada Lovelace"

    request = sent[0]
    assert str(request.url) == "https://inference.runanywhere.ai/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {documented_env['NOTTE_LLM_API_KEY']}"
    body: dict[str, Any] = json.loads(request.content)
    # OpenRouter-only options (`models`, `reasoning`) would be rejected
    assert set(body) <= RUNANYWHERE_FIELDS
