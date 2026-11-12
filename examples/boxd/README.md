# boxd machine with a Notte browser

Serve a web app from a [boxd](https://boxd.sh/?ref=notte) machine and test it with a Notte cloud browser. The browser runs on Notte, with stealth, residential proxies and captcha solving, so pages that challenge a datacenter IP still load.

`main.py` creates an isolated machine, serves a small to-do app on port 8000, and opens it on the machine's HTTPS URL (`machine.access.url`). It turns off the machine's bot protection, so the URL serves the app directly. It then opens the app twice:

1. From this script with Playwright over CDP through `session.page`. It reads the to-do list and saves `output/app.png`.
2. From inside the machine with the [Notte CLI](https://github.com/nottelabs/notte-cli), the way a coding agent on the machine would. It installs the CLI and the Notte skills in `~/.agents/skills`, adds a to-do, and scrapes the page. `NOTTE_API_KEY` goes with each command, so it is not stored on the machine.

The machine's URL is public while the machine exists. Both browser sessions stop and the machine is deleted when the script ends, including after an error. The machine is created with `delete_after=1800`, so boxd deletes it after 30 minutes if the script dies before that.

The script exits with an error if either browser does not see the expected to-dos, or if the machine could not be deleted.

## Run

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/). Copy `.env.template` to `.env` and set `BOXD_API_KEY` and `NOTTE_API_KEY`, then:

```bash
uv sync
uv run main.py
```

Playwright only connects to the remote browser, so `playwright install` is not needed. To test your own app, replace `APP_HTML` and `start_app()`; the URL forwards to whatever listens on port 8000. Optional settings: `BOXD_ORG` picks the organization, `BOXD_REGION` the region (`fra` or `nyc`), and `BOXD_MACHINE_PREFIX` the start of the machine name (`notte-example-` by default).

## Test

`uv run python -m unittest -v test_boxd` runs offline tests of the machine commands and session cleanup. With `BOXD_API_KEY` and `NOTTE_API_KEY` set, it also runs the full flow against real boxd and Notte.
