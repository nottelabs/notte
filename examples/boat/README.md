# boat sandbox with a Notte browser

Serve a web app from a [boat](https://boat.dev) sandbox and test it with a Notte cloud browser. The browser runs on Notte, with stealth, residential proxies and captcha solving, so pages that challenge a datacenter IP still load.

`main.py` creates a sandbox with `NOTTE_API_KEY` in its environment, serves a small to-do app on port 8000, and exposes it on a hosted URL from `host_port`. It then opens the app twice:

1. From this script with Playwright over CDP through `session.page`. It reads the to-do list and saves `output/app.png`.
2. From inside the sandbox with the [Notte CLI](https://github.com/nottelabs/notte-cli), the way a coding agent in the sandbox would. It installs the CLI and the Notte skills in `~/.agents/skills`, adds a to-do, and scrapes the page.

The hosted URL carries an access token, so the browser needs no extra header; the script keeps it out of its printed output. Both browser sessions stop and the sandbox is deleted when the script ends, including after an error.

## Run

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/). Copy `.env.template` to `.env` and set `BOAT_API_KEY` and `NOTTE_API_KEY`, then:

```bash
uv sync
uv run main.py
```

Playwright only connects to the remote browser, so `playwright install` is not needed. To test your own app, replace `APP_HTML` and `start_app()`; `host_port` works for any port your server listens on.

## Test

`uv run python -m unittest -v test_boat` runs offline tests of the sandbox commands and session cleanup. With `BOAT_API_KEY` and `NOTTE_API_KEY` set, it also runs the full flow against real boat and Notte.
