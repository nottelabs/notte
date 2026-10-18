# Yutori Navigator with Notte

Run the official Yutori Python SDK's Navigator n1.5 browser model on a Notte-hosted browser. The original adapter uses Yutori's screenshot, coordinate, keyboard, and request-trimming helpers without copying its implementation.

Use Python 3.12+, install `pip install -r requirements.txt`, and set `NOTTE_API_KEY` and `YUTORI_API_KEY`. Then run `python main.py`. See the [Yutori SDK](https://github.com/yutori-ai/yutori-sdk-python) and [API platform](https://platform.yutori.com).

Call `run(task, start_url)` for your task. The example allows nine core actions: click, type, key press, scroll, navigate, back, forward, refresh, and wait. Other core actions are disabled in the model request. It stops after 12 model turns or a 120-second task deadline, and closes its owned Notte session on success or failure. The deadline includes setup, model calls, screenshots, and all actions; cleanup still waits for owned startup and stop operations to finish. Pass `timeout_seconds` to choose a shorter deadline. A model's final answer is not independent proof that your task succeeded; check your application's result.

Run `python -m unittest test_protocol -v` for native SDK request/response contracts. Set `NOTTE_YUTORI_LIVE=1` and an explicit `NOTTE_API_URL` for `python -m unittest test_browser -v`. These tests execute real Notte screenshot, keyboard, coordinate and navigation actions, including a genuine browser failure and authoritative closed-session checks, using a local model-response fixture. Live Yutori model inference has not been validated.
