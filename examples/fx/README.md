# fx + Notte

Use the [native fx engine](https://fx.sh/docs/lib) from Vercel Labs with a Notte browser. This example uses `libfx` 0.0.14, which embeds fx's Zig engine. Each request owns one Notte session, exposes only `read_page`, and closes the browser after success or failure. The model never receives the CDP credential.

Use Node.js 24+, a [Notte API key](https://console.notte.cc/apikeys), and your configured [AI Gateway](https://vercel.com/docs/ai-gateway) provider for paid model turns.

```sh
npm ci
export NOTTE_API_KEY=your_notte_key
export AI_GATEWAY_API_KEY=your_gateway_key
npm start -- 'Read the title of https://example.com'
```

Set `FX_MODEL` to choose a supported Gateway model. Calls use a 90-second deadline; a three-minute Notte limit bounds interrupted processes. Browser disconnect waits are limited to five seconds, and cancelled tool cleanup finishes before the engine and session close.

## Verify without model charges

```sh
npm run typecheck
npm test
NOTTE_FX_LIVE=1 NOTTE_API_URL=https://api.notte.cc npm test
```

The tests run the actual native fx engine against a scripted model transport. They verify its browser tool call, observed title, safe navigation errors, cancellation, disconnect failures, provider HTTP 401 without retry, and authoritative GET closure of each owned browser. The live command requires only Notte credentials. Paid model turns and hosted deployment remain unverified.

## Terminal fx

For the [fx CLI's native MCP support](https://fx.sh/docs/capabilities/mcp), the included `.mcp.json` points to Notte and reads its bearer token from `NOTTE_API_KEY`. Copy that server entry into your project's existing MCP configuration, export the key, then review and approve this project server:

```sh
fx mcp trust approve notte
fx mcp list --connect
```

After connecting your model provider in fx, ask it to visit a page using Notte. Tell it to stop browsers it creates. The CLI configuration exposes Notte's server toolset; the embedded example instead owns its session in code and limits the model to one page-reading tool. CLI account/model execution is unverified.
