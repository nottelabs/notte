# Laminar with Notte

Trace a Notte browser task in Laminar. Each run opens one cloud browser, records its page title, and closes the session on success or failure.

Set `NOTTE_API_KEY` and `LMNR_PROJECT_API_KEY` in your environment. Get a [Notte key](https://console.notte.cc/apikeys) and a project key from your [Laminar project settings](https://laminar.sh/projects).

Python 3.11+ with uv:

```sh
cd examples/laminar
uv sync --locked
uv run python read_page.py
```

TypeScript with Node.js 24+:

```sh
cd examples/laminar/typescript
npm ci
npm start
```

Pass a URL as the final argument to read another page. The JSON result contains `title`, the closed browser's `session_id`, and `trace_id`. Find the `notte.read_page` span in your Laminar project; its session ID matches the Notte browser.

The example uses manual spans and disables automatic instrumentation. It records the target hostname, title, and browser ID. Authenticated CDP endpoints and raw browser exceptions stay out of the trace. Shutdown flushes pending spans before the command exits.

To test browser success, navigation errors, trace contents, and cleanup without sending traces to Laminar:

```sh
export NOTTE_API_URL=https://api.notte.cc
export NOTTE_LAMINAR_LIVE=1
uv run python -m unittest -v test_read_page.py
cd typescript
npm run typecheck
npm run test:live
```

Set `NOTTE_LAMINAR_EXPORT_LIVE=1` as well to verify that the actual Laminar service stores each language's trace. This needs `LMNR_PROJECT_API_KEY` and reads back the exported span through Laminar's SQL API.
