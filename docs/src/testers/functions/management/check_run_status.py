# @sniptest filename=check_run_status.py
# @sniptest show=9-18
# ruff: noqa: E402 -- hidden live fixture precedes displayed import
import os

from notte_sdk import NotteClient as FixtureClient

function_id = os.environ["NOTTE_FUNCTION_ID"]
completed = FixtureClient().Function(function_id).run(url="https://example.com", stream=False)
run_id = completed.function_run_id
from notte_sdk import NotteClient

client = NotteClient()

# Get run details
run_status = client.functions.get_run(function_id, run_id)

print(f"Status: {run_status.status}")  # "active", "closed", "failed"
print(f"Result: {run_status.result}")
print(f"Session ID: {run_status.session_id}")

assert run_status.function_run_id == run_id
import json

assert json.loads(run_status.result) == {"url": "https://example.com", "search_query": ""}
assert run_status.status == "closed"
