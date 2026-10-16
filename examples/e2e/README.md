# e2e with Notte

Run [e2e](https://e2e.tester.army/docs) web tests on Notte cloud browsers through its native `BrowserProvider` interface.

Use Node.js 24.8+ and a [Notte API key](https://console.notte.cc/apikeys). From this directory, run `npm ci`, set `NOTTE_API_KEY` in your environment, then run `npm test`. No local browser installation or model credentials are needed for the included test.

`e2e.config.ts` selects `notte()` as the browser provider. Change the target's `app.url` to your application; it must be reachable from the cloud browser. Use the native e2e `app`, `screen`, and `expect` APIs in `tests/`.

Each test attempt gets its own browser. The runner releases it after success or failure. Sessions expire after three minutes if the worker crashes. This minimal provider does not implement downloads, provider recordings, or lease sweeping. Per-attempt scope also follows e2e's [configuration and session-state limits](https://e2e.tester.army/docs/browser#pick-a-lease-scope).

For maintainers, `npm run typecheck` checks the adapter and configuration. `npm run test:live` runs the native e2e host against a real Notte browser, checks a page and a deliberate assertion failure, then independently verifies both sessions are closed. `NOTTE_API_URL` can select another Notte environment.

Validation covers deterministic web tests. Model-driven agent steps have not been tested; configure models separately using e2e's [model guide](https://e2e.tester.army/docs/models).
