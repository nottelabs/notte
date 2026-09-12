# @sniptest filename=monitor_runs.py
# @sniptest show=7-33
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os
from json import loads

function_id = os.environ["NOTTE_FUNCTION_ID"]

import time

from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id=function_id)

# Start run
result = function.run(
    url="https://example.com",
    stream=False,  # Don't stream logs
)

run_id = result.workflow_run_id

# Poll status
while True:
    status = client.functions.get_run(function_id, run_id)

    print(f"Status: {status.status}")

    if status.status in ["closed", "failed"]:
        print(f"Final result: {status.result}")
        break

    time.sleep(5)  # Check every 5 seconds

assert status.status == "closed"
assert status.function_run_id == run_id
assert loads(status.result) == {"url": "https://example.com", "search_query": ""}
run_status = status
