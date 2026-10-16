# Braintrust with Notte

Trace a real browser task in Braintrust. Both examples record the page title, Notte session ID, timing, and errors, then flush the trace before exiting. They close the browser on success and failure and return a link to the trace.

Set `NOTTE_API_KEY` ([Notte](https://console.notte.cc/apikeys)) and `BRAINTRUST_API_KEY` ([Braintrust](https://www.braintrust.dev/app/~/configuration/org/api-keys)). Set `BRAINTRUST_PROJECT` to your project name, or use the default `notte-integration-tests`. Braintrust creates the project if it does not exist. A model-provider key is not required.

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

Pass a URL as an argument to trace another task. Both examples return `title`, `session_id`, `span_id`, and `trace_url`. Open the link to inspect the trace; its metadata includes the owned Notte session ID. Keep your existing LLM instrumentation inside the browser span to correlate model calls with browser work.

Run the four live cases from `typescript` after installing both projects:

```sh
NOTTE_BRAINTRUST_PYTHON=../.venv/bin/python npm run test:live
```

The tests execute both original recipes, read successful and failed traces back through Braintrust's API, and independently verify that every owned browser closes. They require both API keys and skip when either is absent. Set `NOTTE_API_URL` to choose another Notte environment; set `BRAINTRUST_API_URL` for your organization's data-plane region if needed.
