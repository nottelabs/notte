# Vercel Eve + Notte

An original [Eve authored tool](https://eve.dev/docs/tools) opens a Notte browser, reads a page title with Playwright, and closes its session before returning. Eve discovers `agent/tools/read_page.ts` as `read_page`. The model receives a URL argument and a title; the CDP credential stays in your app runtime.

Use Node.js 24+ and a [Notte API key](https://console.notte.cc/apikeys).

```sh
npm ci
export NOTTE_API_KEY=your_notte_key
npm run typecheck
npm test
NOTTE_EVE_LIVE=1 NOTTE_API_URL=https://us-dev.notte.cc npm test
```

The offline tests compile the native Eve manifest and check navigation, errors, and cancellation. The live tests run the authored tool against Notte, inject disconnect failures, and independently GET each owned session to verify closure. Disconnect waits are limited to five seconds. No model key is needed for these tests. A three-minute session limit bounds interrupted processes.

To use the tool in an existing Eve app, install `notte-sdk` and `playwright-core`, copy `agent/tools/read_page.ts`, and set `NOTTE_API_KEY` in that app's server environment. For this example, choose your model in `agent/agent.ts`, then run `npm run dev` and connect your model provider through Eve. Ask it to read the title of `https://example.com`.

Paid model turns and hosted deployment remain unverified. The tests exercise native compilation and the tool executor, not a model's decision to call it. Keep your normal Eve channel authentication and tool approval policy when exposing the agent to others.
