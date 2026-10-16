# OpenAI Computer Use with Notte

Connect the Responses API's native `computer` tool to a Notte browser through Playwright over CDP. Original Python and TypeScript adapters execute ordered action batches and return PNG screenshots at the viewport's original resolution. No local browser installation is required.

Set `NOTTE_API_KEY` ([Notte](https://console.notte.cc/apikeys)) and `OPENAI_API_KEY` ([OpenAI](https://platform.openai.com/api-keys)). The demo uses `gpt-6.1-sol`; real model requests incur OpenAI API charges.

From this directory:

```sh
# Python 3.11+, uv
uv sync --locked
uv run python python/demo.py

# TypeScript, Node.js 24+
cd typescript
npm ci
npm start
```

The model reads a random code from a screenshot and submits it through a form. Each demo verifies the actual input and page result, returns `output`, `session_id`, and `actions`, and closes its browser on success or error.

`python/notte_computer.py` and `typescript/src/computer.ts` support screenshots, click, double-click, move, scroll, drag, typing, key presses, and wait. Provide an explicit Playwright viewport and a permission callback. Pending API safety checks stop execution for human review. The demo permits actions only on its own `about:blank` fixture; replace that policy before adapting it to other sites or consequential actions. Page content cannot grant permission. Runs stop after eight computer turns, 64 actions, or the time limit.

Run real browser protocol, permission-refusal, provider-401 cleanup, and optional model tests:

```sh
uv run python -m unittest discover -s python -p test_live.py -v
cd typescript
npm run typecheck
npm run test:live
```

Browser tests require `NOTTE_API_KEY`. The optional model case also requires `OPENAI_API_KEY`; other cases make no paid requests. Set `NOTTE_API_URL` to select another Notte environment.

API reference: [OpenAI Computer Use](https://developers.openai.com/api/docs/guides/tools-computer-use).
