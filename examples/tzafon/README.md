# Tzafon Lightcone with Notte

Run Northstar's computer-use loop on an owned Notte browser through the official Lightcone SDKs. This example copies a visible random code into an isolated local form and checks the DOM result. It does not provision a Lightcone computer.

Set `NOTTE_API_KEY` and `TZAFON_API_KEY` in your shell.

Python 3.11+, from this directory:

```sh
uv sync --locked
uv run --locked python python/demo.py
```

Node.js 24+, from `typescript`:

```sh
npm ci
npm start
```

The result contains `output: "Accepted"`, the performed action names, and the stopped browser's session ID. The model must actually complete the form before success is reported.

The form supports left click, point-and-type, typing, Enter/Tab, wait, and screenshots. Other actions and pending safety checks stop the run. The loop allows eight action turns, checks approval before each action, and converts Northstar's 0–999 coordinates to viewport pixels. Screenshots remain at their original CSS dimensions. Response persistence is disabled; each turn sends the accumulated conversation.

## Verification

Run `uv run --locked python -m unittest discover -s python` and, from `typescript`, `npm test` for native SDK wire contracts, coordinate boundaries, limits, denied actions, and cancellation.

Set `NOTTE_TZAFON_PYTHON` to this directory's `.venv/bin/python`, then run `npm run test:live` from `typescript`. These tests use real Notte browsers and injected Lightcone HTTP responses for form completion, SDK HTTP 401 handling, pending safety checks, and invalid coordinates. Each case independently verifies that its owned session is closed. CI requires the Notte key and tests both published and source SDKs.

The pinned SDK declarations still name the older computer tool; the examples send `computer_use` from the [current API documentation](https://docs.lightcone.ai/guides/responses-api/). Wire tests enforce that body and history format. Live Tzafon model inference, perception, and hosted API acceptance have not been tested.
