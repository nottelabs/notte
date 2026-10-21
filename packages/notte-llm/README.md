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

The async client posts Chat Completions through `httpx` with a 60-second timeout per attempt
(`LLMEngine(timeout=...)`), retrying
transient errors after 2 and 5 seconds. Typed extraction tries strict `json_schema` output;
when a provider rejects it, the client retries with `json_object` and the schema in the prompt.
If the endpoint also rejects `json_object`, it uses the schema in the prompt alone. Every
answer is still validated with Pydantic, with JSON repair and parsing feedback on retries.
Instructions-only extraction starts with `json_object` because it has no fixed data schema.

OpenRouter receives model fallbacks (`google/gemini-3.8-flash`, `openai/gpt-4.1-mini`).
`LLMEngine(provider_order=[...], reasoning={...})` can also pass OpenRouter routing and reasoning
options. These extras are sent only when the configured hostname is `openrouter.ai`.
A provider's content-policy refusal (an OpenRouter, OpenAI or Azure content-filter error, or a
`content_filter` finish reason with no content) raises `ContentFilterError` naming the model,
not `InvalidAPIKeyError`.
For Vertex or other token-based endpoints, mint the access token outside the library and pass
it as `NOTTE_LLM_API_KEY`; refresh it before it expires.

For endpoint-specific request options, pass `extra_body` to `LlmExtractor.extract`
(or to `LLMEngine`'s constructor). These explicit fields override request defaults
for that call; `None` removes a default field. For example, pin Together without
model or provider fallbacks and use its advertised output-token limit:

```python
result = await LlmExtractor(model="meta-llama/llama-3.3-70b-instruct").extract(
    url="https://example.com",
    document="# Example page",
    response_format=Title,
    instructions="Extract the title",
    extra_body={
        "models": None,
        "provider": {"order": ["together"], "allow_fallbacks": False},
        "max_completion_tokens": 2048,
    },
)
```

Explicit extras are forwarded to any configured endpoint, so use only fields that
endpoint supports. The library does not discover provider limits or automatically
lower its default 8192 completion tokens. Set `max_completion_tokens` to your
endpoint's limit when it is lower. Overrides do not persist to subsequent calls.

## Deciders for `session.act()`, `choose()` and `check()`

`notte_llm.act` provides the deciders of `session.act()` / `choose()` / `check()` (see the
[act docs](https://docs.notte.cc/features/sessions/act)):

- `JevDecider`: TypeSafe's Jev classification model, through OpenRouter's decisions endpoint (alpha:
  `https://openrouter.ai/api/alpha/decisions`, model `~typesafe/jev-latest`, `OPENROUTER_API_KEY`) or on TypeSafe
  directly (`/v1/systemone`, `TYPESAFE_API_KEY`, `TYPESAFE_BASE_URL`). `TYPESAFE_MODEL` overrides the model of either.
- `LlmDecider`: a model of the endpoint above, one call per decision with the options as JSON-schema enums.
- `LlmWriter`: the field writer of both, answering exactly `{"text": ...}`.

`default_decider()` uses Jev on TypeSafe when `TYPESAFE_API_KEY` is set, else Jev through OpenRouter with an
OpenRouter key, else `LlmDecider` on another `NOTTE_LLM_*` endpoint (`NOTTE_ACT_MODEL`, then `NOTTE_LLM_MODEL`,
then `google/gemini-3.1-flash-lite`). `NOTTE_ACT_DECIDER=jev|llm` forces one (`llm` keeps an LLM deciding with an
OpenRouter key). Jev cannot write text: the writer model is `NOTTE_ACT_TEXT_MODEL`, else `inception/mercury-3` on
OpenRouter, else the decision model. When the writer's provider refuses a value on content-policy grounds,
`NOTTE_ACT_MODEL` (default `google/gemini-3.1-flash-lite`) writes it instead. Deciders and the writer see elements
by their accessible names and the page as visible text by default (`NOTTE_ACT_LABELS=html` for the rendered HTML). Decisions are sent
without OpenRouter model fallbacks and with reasoning disabled (`NOTTE_ACT_REASONING=none`; models that require
reasoning are retried with `low`).

The question set, prompts and guards are adapted from [jev-ultrafast](https://github.com/browser-use/jev-ultrafast)
(MIT License, Copyright (c) 2026 Browser Use); the license text ships as `notte_core/act/LICENSE-jev-ultrafast`.
