# Daytona sandbox with a Notte browser

Serve a web app from a [Daytona](https://www.daytona.io) sandbox and test it with a Notte cloud browser. Chromium runs on Notte, so the sandbox's memory stays free for the agent's code.

`main.py` creates a sandbox, serves a small to-do app on port 3000, and exposes it on a signed preview URL from `sandbox.create_signed_preview_url(3000)`. It then opens the app twice:

1. From this script with Playwright over CDP through `session.page`. It reads the to-do list and saves `output/app.png`.
2. From inside the sandbox with the [Notte CLI](https://github.com/nottelabs/notte-cli), the way a coding agent in the sandbox would. It installs the CLI and the Notte skills in `~/.agents/skills`, adds a to-do, and scrapes the page.

Both browser sessions send the `X-Daytona-Skip-Preview-Warning` header, which skips the warning page Daytona shows browsers on a preview URL's first load. Both sessions stop and the sandbox is deleted when the script ends, including after an error.

## Run

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/). Copy `.env.template` to `.env` and set `DAYTONA_API_KEY` and `NOTTE_API_KEY`, then:

```bash
uv sync
uv run main.py
```

Playwright only connects to the remote browser, so `playwright install` is not needed. To test your own app, replace `APP_HTML` and `start_app()`; a signed preview URL works for any port your server listens on.

## Test

`uv run python -m unittest -v test_daytona` runs offline tests of the sandbox commands and session cleanup. With `DAYTONA_API_KEY` and `NOTTE_API_KEY` set, it also runs the full flow against real Daytona and Notte.
