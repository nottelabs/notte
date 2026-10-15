"""litellm (and the provider SDKs it imports) loads on the first LLM call, not when a browser session is set up."""

import os
import subprocess
import sys

# Session, scraping, action listing and the LLM service, built but never asked to call a model.
NO_LLM_CALL = """
import sys
from notte_browser.session import NotteSession
from notte_browser.scraping.schema import SchemaScrapingPipe
from notte_browser.tagging.action.llm_taging.base import RetryPipeWrapper
from notte_llm.engine import LLMEngine
from notte_llm.service import LLMService
_ = LLMService()
print("LOADED:" + ",".join(name for name in ("litellm", "openai", "llamux") if name in sys.modules))
"""

FIRST_LLM_CALL = """
import asyncio
import sys
from unittest.mock import patch
from notte_llm.engine import LLMEngine
from notte_llm.service import LLMService

async def main():
    service = LLMService(base_model="openai/gpt-4o-mini", use_router=False)
    _ = service.estimate_tokens(text="hello")
    import litellm
    from litellm import ModelResponse
    reply = ModelResponse(choices=[{"message": {"role": "assistant", "content": "hi"}}])
    with patch("litellm.acompletion", return_value=reply):
        response = await LLMEngine(model="openai/gpt-4o-mini").completion([{"role": "user", "content": "hi"}])
    print("CONTENT:" + response.choices[0].message.content)

asyncio.run(main())
"""


def run(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "DISABLE_TELEMETRY": "true", "DISABLE_NOTTE_LLM_TRACING": "true"},
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return result.stdout


def test_setting_up_a_session_does_not_import_litellm() -> None:
    lines = [line for line in run(NO_LLM_CALL).splitlines() if line.startswith("LOADED:")]
    assert lines == ["LOADED:"]


def test_the_first_llm_call_still_works() -> None:
    assert "CONTENT:hi" in run(FIRST_LLM_CALL)
