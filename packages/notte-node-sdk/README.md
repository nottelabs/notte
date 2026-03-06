# @notte/sdk — Node.js SDK for Notte

Node.js/TypeScript SDK for the [Notte](https://notte.cc) browser automation API. Mirrors the [Python SDK](../notte-sdk/) with idiomatic JavaScript patterns.

## Requirements

- Node.js 18+ (uses native `fetch`)
- A Notte API key ([get one here](https://console.notte.cc))

## Installation

```bash
npm install @notte/sdk
```

## Quick Start

Set your API key:

```bash
export NOTTE_API_KEY="your-api-key"
```

### High-level: `RemoteSession.use()` (recommended)

Auto-starts and auto-stops the session, even on errors:

```ts
import { NotteClient, RemoteSession } from "@notte/sdk";

const client = new NotteClient();

const markdown = await RemoteSession.use(client.sessions, {}, async (session) => {
  await session.execute({ type: "goto", url: "https://example.com" });
  const result = await session.scrape({ only_main_content: true });
  return result.markdown;
});

console.log(markdown);
```

### Low-level: `SessionsClient` direct usage

```ts
import { NotteClient } from "@notte/sdk";

const client = new NotteClient();

// Start a session
const session = await client.sessions.start({ headless: true });
console.log("Session ID:", session.session_id);

// Navigate and scrape
await client.sessions.execute(session.session_id, {
  type: "goto",
  url: "https://example.com",
});

const data = await client.sessions.scrape(session.session_id, {
  only_main_content: true,
});
console.log(data.markdown);

// Stop
await client.sessions.stop(session.session_id);
```

### `await using` (Node 22+ / TypeScript 5.2+)

```ts
import { NotteClient } from "@notte/sdk";

const client = new NotteClient();

await using session = client.session();
await session.start();
await session.execute({ type: "goto", url: "https://example.com" });
const data = await session.scrape();
// session.stop() called automatically
```

## Configuration

```ts
const client = new NotteClient({
  apiKey: "your-key",         // or set NOTTE_API_KEY env var
  serverUrl: "https://...",   // defaults to https://api.notte.cc
  timeoutMs: 30_000,          // request timeout, defaults to 60s
});
```

## API Reference

### `NotteClient`

| Method | Description |
|---|---|
| `sessions` | Access the `SessionsClient` for direct API calls |
| `session(options?)` | Create a `RemoteSession` (call `.start()` to begin) |
| `healthCheck()` | Check API connectivity |

### `SessionsClient`

| Method | Description |
|---|---|
| `start(params?)` | Start a new browser session |
| `stop(sessionId)` | Stop a session |
| `status(sessionId)` | Get session status |
| `list(params?)` | List sessions |
| `scrape(sessionId, params?)` | Scrape page content |
| `observe(sessionId, params?)` | Observe page actions |
| `execute(sessionId, action)` | Execute a browser action |
| `setCookies(sessionId, cookies)` | Set cookies |
| `getCookies(sessionId)` | Get cookies |

### `RemoteSession`

| Method | Description |
|---|---|
| `start()` | Start the session |
| `stop()` | Stop the session |
| `scrape(params?)` | Scrape current page |
| `observe(params?)` | Observe current page |
| `execute(action)` | Execute an action |
| `RemoteSession.use(client.sessions, opts, fn)` | Auto-managed lifecycle |
| `RemoteSession.fromId(client, id)` | Attach to existing session |

## License

MIT
