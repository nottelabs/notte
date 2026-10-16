# Notte LLM

LLM-based structured data extraction for Notte. It provides `LlmExtractor`, the default implementation of the
`notte_core.extraction.StructuredExtractor` protocol that local sessions use for
`scrape(instructions=..., response_format=...)`. Cloud sessions run extraction server side and don't need it.

```bash
pip install 'notte[llm]'  # or: pip install notte-llm
```

```python
from notte_browser.session import NotteSession
from notte_llm import LlmExtractor
from pydantic import BaseModel


class Title(BaseModel):
    title: str


with NotteSession(headless=True, extractor=LlmExtractor()) as session:
    _ = session.execute(type="goto", url="https://www.notte.cc")
    data = session.scrape(response_format=Title)
```

When `notte-llm` is installed and no extractor is passed, sessions use `LlmExtractor()` automatically.

Set `OPENROUTER_API_KEY` to use OpenRouter with `google/gemini-3.5-flash-lite` by default.
For another OpenAI-compatible endpoint, set all three of `NOTTE_LLM_BASE_URL`,
`NOTTE_LLM_API_KEY`, and `NOTTE_LLM_MODEL` (the endpoint's own model ID):

- OpenAI: `NOTTE_LLM_BASE_URL=https://api.openai.com/v1`, `NOTTE_LLM_MODEL=gpt-4o`.
- Gemini: `NOTTE_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`, `NOTTE_LLM_MODEL=gemini-3.5-flash-lite`.
- Ollama/custom: `NOTTE_LLM_BASE_URL=http://localhost:11434/v1`, your local model ID, and `NOTTE_LLM_API_KEY=ollama` for an unauthenticated local server. Ollama has not been live-tested.

`NOTTE_LLM_API_KEY` overrides `OPENROUTER_API_KEY`. The latter is used only at the default
OpenRouter URL, so it is never sent to a custom endpoint. The per-call `model=` argument
selects a model at the configured endpoint without translating its ID.

| Variable | Default |
| --- | --- |
| `NOTTE_LLM_BASE_URL` | `https://openrouter.ai/api/v1` |
| `NOTTE_LLM_API_KEY` | `OPENROUTER_API_KEY` at the default URL; required elsewhere |
| `NOTTE_LLM_MODEL` | `google/gemini-3.5-flash-lite` at the default URL; required elsewhere |
| `NOTTE_LLM_TEMPERATURE` | `0.0` |
| `NOTTE_LLM_NB_RETRIES_STRUCTURED_OUTPUT` | `2` |
| `NOTTE_LLM_CONTEXT_TOKENS` | `128000` (document clipping estimates four characters per token) |

The async client posts Chat Completions through `httpx` with a 60-second timeout, retrying
transient errors after 2 and 5 seconds. Typed extraction tries strict `json_schema` output;
when a provider rejects it, the client retries with `json_object` and the schema in the prompt.
If the endpoint also rejects `json_object`, it uses the schema in the prompt alone. Every
answer is still validated with Pydantic, with JSON repair and parsing feedback on retries.
Instructions-only extraction starts with `json_object` because it has no fixed data schema.

OpenRouter receives model fallbacks (`google/gemini-3.8-flash`, `openai/gpt-4.1-mini`).
`LLMEngine(provider_order=[...], reasoning={...})` can also pass OpenRouter routing and reasoning
options. These extras are sent only when the configured hostname is `openrouter.ai`.
For Vertex or other token-based endpoints, mint the access token outside the library and pass
it as `NOTTE_LLM_API_KEY`; refresh it before it expires.
