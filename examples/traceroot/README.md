# traceroot with Notte

Trace an AI agent that browses with Notte in [traceroot](https://traceroot.ai). Each example gives an agent a Notte browser through Notte Browser MCP, asks it for the top 3 Hacker News stories with their points, and traces the run: each model call with its tokens and cost, and each Notte tool call with what the browser returned.

| Framework | File | Model key |
|---|---|---|
| OpenAI Agents SDK (Python) | `hn_openai.py` | `OPENAI_API_KEY` |
| Claude Agent SDK (Python) | `hn_claude.py` | `ANTHROPIC_API_KEY` |
| Vercel AI SDK (TypeScript) | `typescript/src/hn_vercel_ai.ts` | `ANTHROPIC_API_KEY` |

Set `NOTTE_API_KEY`, `TRACEROOT_API_KEY`, and the model key for your framework. Get a [Notte key](https://console.notte.cc/apikeys) and a project key from [traceroot](https://app.traceroot.ai). If you self-host traceroot, also set `TRACEROOT_HOST_URL` to your API's origin.

Python 3.11 to 3.13 with uv:

```sh
cd examples/traceroot
uv sync --locked
uv run python hn_openai.py   # or hn_claude.py
```

TypeScript with Node.js 24+:

```sh
cd examples/traceroot/typescript
npm ci
npm start
```

Each prints `stories`, `trace_id`, and the closed browser's `session_id`. To print the trace's span tree and its link in the traceroot web app:

```sh
npx -y traceroot-cli@latest login --api-key "$TRACEROOT_API_KEY"
npx -y traceroot-cli@latest traces get <trace_id>
```

## Prompt regression

`uv run python hn_openai.py --broken` swaps in instructions that tell the agent to skip scraping and answer from memory. Use it to see a traceroot detector flag answers that aren't grounded in the page, and `hn_eval.py --broken` to compare it with the fixed agent.

## Notes

- `traceroot.initialize(integrations=[Integration.OPENAI_AGENTS])` replaces the OpenAI Agents SDK's default trace exporter, so the spans go to traceroot instead of OpenAI. Leave the SDK's tracing on: `RunConfig(tracing_disabled=True)` drops them.
- `traceroot.initialize(integrations=[Integration.CLAUDE_AGENT_SDK])` wraps `claude_agent_sdk.query`. Call it through the module, as `hn_claude.py` does; a `query` imported by name before `initialize()` is not traced.
- The Vercel AI SDK reports through its own OpenTelemetry integration, registered with `registerTelemetry(new OpenTelemetry({ usage: true }))` after `TraceRoot.initialize()`.
- The Notte key travels in the MCP connection's header, which the traces do not record.
- The Python examples run under `asyncio.Runner`. `notte_sdk` enables `nest_asyncio` on import, and only closing the loop stops the Claude Agent SDK's worker threads, so the process can exit.
- Python 3.14 is not supported yet: with `nest_asyncio` enabled, the MCP client cannot detect the running event loop.
