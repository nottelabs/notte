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

Copy the `.env.example` file to `.env` and fill in your API keys. Note that by default, `notte` uses `groq/llama-3.3-70b-versatile`. So you need to set the `GROQ_API_KEY` environment variable in your `.env` file. You can set up this key by creating a [GROQ account](https://groq.com/docs/api-reference/introduction) and creating an API key.

```sh
cp .env.example .env
```

Notte uses `litellm` to interface with multiple LLM providers. You can also set other API keys in your `.env` file to use other LLM providers (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
