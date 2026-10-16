# Vibium with Notte

Run the native Vibium Python or TypeScript client against a browser owned by Notte. A loopback discovery adapter lets local ChromeDriver attach to Notte's authenticated CDP connection and provide the native BiDi endpoint Vibium uses.

This integration is a draft. Hosted Notte availability is not verified yet. Use an environment that supports native BiDi attachment; an ordinary CDP connection alone is insufficient.

Requires Linux or macOS, Python 3.11+ or Node.js 24+, a [Notte API key](https://console.notte.cc/api-keys), and a local [ChromeDriver](https://googlechromelabs.github.io/chrome-for-testing/) matching the hosted browser's major version. Chrome runs on Notte; no local Chrome installation is needed. The recipes pin Vibium 26.8.21.

From this directory, set `NOTTE_API_KEY` and `CHROMEDRIVER_PATH` to your key and the downloaded executable. Set `NOTTE_API_URL` when selecting a different Notte environment.

```bash
uv sync --locked
uv run --no-sync python demo.py
```

For TypeScript:

```bash
npm ci
npm start
```

Both recipes read Example Domain, save `screenshot.png`, reconnect through the native client, and close the Notte session. Keep application tasks inside `notte_vibium` or `withNotteVibium` so cleanup also runs after errors or cancellation. The native client can take up to 125 seconds to finish a cancelled startup; Notte stops before this local cleanup finishes.

Run offline transport and cleanup tests with `uv run --no-sync python -m unittest test_bridge test_cleanup` and `npm test`. CI also exercises both native clients against an isolated local Chrome browser, including form actions, screenshots, reconnects, failure, and cancellation.

Opt into actual Notte tests with `NOTTE_VIBIUM_LIVE=1`, then run `uv run --no-sync python -m unittest test_live test_cli` and `npm run test:live`. These require working platform support and independently GET-confirm each owned session closed. Signal tests persist an owned-session journal in the temporary directory before interruption; `VIBIUM_OWNERSHIP_JOURNAL` selects its path. The workflow's manual hosted job runs this acceptance suite; an unrun hosted job does not establish platform availability.
