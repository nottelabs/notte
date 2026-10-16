# Local Setup of Notte

To install `notte` locally, run the following commands:
```sh
uv sync --dev --all-extras
uv run pre-commit install
```

`notte` uses `patchright` to automate browser interactions. If you haven't already, you'll need to install the browsers you want to use, e.g. using chromium:

```sh
uv run patchright install --with-deps chromium
```

Copy the `.env.example` file to `.env` and fill in your API keys (at least `NOTTE_API_KEY` to use the cloud SDK).

```sh
cp .env.example .env
```

The optional `notte[llm]` extra provides local structured scraping over an async OpenAI-compatible HTTP client.

Set `OPENROUTER_API_KEY` to use OpenRouter with `google/gemini-3.5-flash` by default.
For another OpenAI-compatible endpoint, set all three of `NOTTE_LLM_BASE_URL`,
`NOTTE_LLM_API_KEY`, and `NOTTE_LLM_MODEL` (the endpoint's own model ID):

- OpenAI: `NOTTE_LLM_BASE_URL=https://api.openai.com/v1`, `NOTTE_LLM_MODEL=gpt-4o`.
- Gemini: `NOTTE_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`, `NOTTE_LLM_MODEL=gemini-3.5-flash`.
- Ollama/custom: `NOTTE_LLM_BASE_URL=http://localhost:11434/v1`, your local model ID, and `NOTTE_LLM_API_KEY=ollama` for an unauthenticated local server. Ollama has not been live-tested.

`NOTTE_LLM_API_KEY` overrides `OPENROUTER_API_KEY`. The latter is used only at the default
OpenRouter URL, so it is never sent to a custom endpoint. The per-call `model=` argument
selects a model at the configured endpoint without translating its ID.
