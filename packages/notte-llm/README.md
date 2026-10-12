# Notte LLM

LLM-based structured data extraction for Notte. It provides `LlmExtractor`, the default implementation of the
`notte_core.data.extraction.StructuredExtractor` protocol that local sessions use for
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


with NotteSession(headless=True, extractor=LlmExtractor(model="openai/gpt-4o")) as session:
    _ = session.execute(type="goto", url="https://www.notte.cc")
    data = session.scrape(response_format=Title)
```

When `notte-llm` is installed and no extractor is passed, sessions use `LlmExtractor()` automatically. Settings come
from the environment:

| Variable | Default |
| --- | --- |
| `NOTTE_LLM_MODEL` | `vertex_ai/gemini-3.5-flash` with `GOOGLE_APPLICATION_CREDENTIALS`, else `gemini/gemini-3.5-flash` |
| `NOTTE_LLM_NB_RETRIES_STRUCTURED_OUTPUT` | `2` |
| `NOTTE_LLM_TEMPERATURE` | `0.0` |

The provider API key (e.g. `GEMINI_API_KEY`, `OPENAI_API_KEY`) is read by LiteLLM from the environment.
