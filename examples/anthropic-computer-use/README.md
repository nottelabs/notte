# Anthropic Computer Use with Notte

Run Anthropic's native `computer_toolset_20260801` against a Notte browser viewport. The examples implement screenshot, click, typing, key presses, and wait through Playwright over CDP. They do not control an operating-system desktop. The SDK disables unimplemented members and handles tool results.

Set `NOTTE_API_KEY` ([Notte](https://console.notte.cc/apikeys)) and `ANTHROPIC_API_KEY` ([Claude Console](https://platform.claude.com/settings/keys)) in your environment. Model requests incur Anthropic API charges. No local browser installation is needed.

From this directory:

```sh
# Python 3.11+, uv
export NOTTE_ENABLE_NEST_ASYNCIO=false
uv sync --locked
uv run python python/demo.py

# TypeScript, Node.js 24+
cd typescript
npm ci
npm start
```

The pinned Python SDK 1.10.0 needs `NOTTE_ENABLE_NEST_ASYNCIO=false` to use an unmodified asyncio event loop.

Both examples use Claude Haiku 5.5 to read a random code from a screenshot, enter it into a form, and submit. They check the actual page result before returning `output`, `session_id`, and `calls`. The outer Notte session owner stops the browser on success and failure.

`python/notte_computer.py` and `typescript/src/computer.ts` expose reusable toolsets. Provide your Playwright page with an explicit viewport and a confirmation callback. The demo approves typing and key presses only on its own `about:blank` fixture. Adapt that policy before connecting it to other pages.

Run real browser protocol, permission-refusal, provider-401 cleanup, and optional real-model tests:

```sh
uv run python -m unittest discover -s python -p test_live.py -v
cd typescript
npm run typecheck
npm run test:live
```

Browser tests require `NOTTE_API_KEY`. The real-model case additionally requires `ANTHROPIC_API_KEY`; the other cases make no paid model calls. Set `NOTTE_API_URL` to select another Notte environment.
