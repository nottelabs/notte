# Deep Agents with Notte

Run LangChain Deep Agents with three Notte MCP browser tools. Each run owns one cloud browser session and closes it on success or failure.

Set `NOTTE_API_KEY` and a funded `ANTHROPIC_API_KEY` in your environment. Create keys at [Notte](https://console.notte.cc/apikeys) and [Anthropic](https://platform.claude.com/settings/keys). The default model is `claude-haiku-5-5`; override it with `DEEPAGENTS_MODEL`.

Python 3.11+ with uv:

```sh
cd examples/deepagents
uv sync --frozen
uv run python agent.py "Visit https://example.com and report its page title."
```

TypeScript with Node.js 24+:

```sh
cd examples/deepagents/typescript
npm ci
npm start -- "Visit https://example.com and report its page title."
```

The result contains the answer and the closed browser's `session_id`. The MCP adapter receives only Notte's `browser_action`, `browser_observe`, and `browser_scrape` tools. Every browser call is bound to the owned session ID. Deep Agents uses its in-memory filesystem backend with only `read_file` enabled.

To verify actual model navigation, provider authentication failure, and browser cleanup, choose your API endpoint explicitly and opt in:

```sh
export NOTTE_API_URL=https://api.notte.cc
export NOTTE_DEEPAGENTS_LIVE=1
export NOTTE_DEEPAGENTS_MODEL_LIVE=1
uv run python -m unittest -v test_agent.py
cd typescript
npm run typecheck
npm run test:live
```

Without `NOTTE_DEEPAGENTS_MODEL_LIVE=1`, the live suite verifies provider HTTP 401 failures and cleanup with real Notte sessions and MCP connections. Python also verifies cancellation. Navigation tests independently inspect the persisted browser history before accepting the model's answer.
