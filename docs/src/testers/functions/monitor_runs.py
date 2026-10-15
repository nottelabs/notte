# @sniptest filename=monitor_runs.py
# @sniptest show=7-39
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os
from json import loads

function_id = os.environ["NOTTE_FUNCTION_ID"]

import time
from concurrent.futures import ThreadPoolExecutor

from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id=function_id)

# Create the run first so you know its ID
run_id = function.create_run().function_run_id

# run() blocks until completion; keep its exception visible to the polling thread.
with ThreadPoolExecutor(max_workers=1) as executor:
    execution = executor.submit(
        function.run,
        function_run_id=run_id,
        url="https://example.com",
        stream=False,
    )

    # Poll status while it runs
    while True:
        if execution.done():
            execution.result()  # Propagate a rejected start instead of polling forever.
        status = client.functions.run_get_metadata(function_id, run_id)
        print(f"Status: {status.status}")
        if status.status in ["closed", "failed"]:
            print(f"Final result: {status.result}")
            break
        time.sleep(5)  # Check every 5 seconds

    execution.result()

assert status.status == "closed"
assert status.function_run_id == run_id
assert status.result is not None
assert loads(status.result) == {"url": "https://example.com", "search_query": ""}
run_status = status
