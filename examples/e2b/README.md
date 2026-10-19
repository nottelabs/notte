# E2B sandbox with a Notte browser

Serve a web app from an [E2B](https://e2b.dev) sandbox and test it with a Notte cloud browser. Chromium runs on Notte, so the sandbox installs no browser.

`main.py` creates a sandbox, serves a small to-do app on port 8000, and exposes it at `https://{sandbox.get_host(8000)}`. It then opens the app twice:

1. From this script with Playwright over CDP through `session.page`. It reads the to-do list and saves `output/app.png`.
2. From inside the sandbox with the [Notte CLI](https://github.com/nottelabs/notte-cli), the way a coding agent in the sandbox would. It installs the CLI and the Notte skills in `~/.agents/skills`, adds a to-do, and scrapes the page.

Both browser sessions stop and the sandbox is killed when the script ends, including after an error.

## Run

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/). Copy `.env.template` to `.env` and set `E2B_API_KEY` and `NOTTE_API_KEY`, then:

```bash
uv sync
uv run main.py
```

Playwright only connects to the remote browser, so `playwright install` is not needed. To test your own app, replace `APP_HTML` and `start_app()`; any server on a sandbox port is reachable at `https://{sandbox.get_host(port)}`.

## Test

`uv run python -m unittest -v test_e2b` runs offline tests of the sandbox commands and session cleanup. With `E2B_API_KEY` and `NOTTE_API_KEY` set, it also runs the full flow against real E2B and Notte.
