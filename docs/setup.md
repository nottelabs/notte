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

The optional `notte[llm]` extra (structured scraping on local sessions) uses `litellm` to interface with multiple LLM providers. Set the API key of the provider you use in your `.env` file (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) and pick the model with `NOTTE_LLM_MODEL` (see [change_local_config.md](change_local_config.md)).
