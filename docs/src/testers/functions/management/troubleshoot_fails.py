# @sniptest filename=troubleshoot_fails.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="func_abc123")

run = client.functions.run_get_metadata("func_abc123", "run_xyz789")

if run.status == "failed":
    print(f"Error: {run.result}")

    # Run the function to get a replay
    result = function.run(url="https://example.com", raise_on_failure=False)
    replay = function.replay()
    replay.download("debug_replay.mp4")
