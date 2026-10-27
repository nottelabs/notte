# OpenAGI Lux with Notte

Run the official [OpenAGI Lux Python SDK](https://github.com/agiopen-org/oagi-python) on a Notte cloud browser. The original adapter implements its screenshot and action-handler interfaces with Playwright over CDP.

Use Python 3.11+, [uv](https://docs.astral.sh/uv/), a [Notte API key](https://console.notte.cc/apikeys), and an [OpenAGI API key](https://developer.agiopen.org/api-keys).

From this directory, run `uv sync --locked`, set `NOTTE_API_KEY`, `OAGI_API_KEY` and `NOTTE_ENABLE_NEST_ASYNCIO=false` in your environment, then run `uv run --locked python demo.py`. No local browser or desktop automation package is needed.

The demo asks the native `AsyncDefaultAgent` to copy a random code into an isolated browser form. It blocks external page requests, approves only the actions that form needs, checks the result, and closes its browser on success or error. Execution is limited to eight model steps and two minutes. The demo suppresses SDK diagnostics and reports safe provider status and the session ID on failure.

`notte_computer.py` maps Lux's normalized coordinates, clicks, typing, hotkeys, scrolling, and dragging to one browser viewport. Every action requires a confirmation callback. Failure and human-review actions stop execution. To use another application, replace the fixture and confirmation policy with ones appropriate to your task.

For maintainers, `uv run --locked python -m unittest test_live -v` requires only `NOTTE_API_KEY`. It runs the real Lux SDK against a local protocol server and real Notte browsers, covering screenshot uploads, form actions, refusal, HTTP 401, and independent session closure. `NOTTE_API_URL` selects another Notte environment.

Live Lux model inference has not been tested. These checks validate SDK protocol and browser behavior without calling OpenAGI's hosted model.
