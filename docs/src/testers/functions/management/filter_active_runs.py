# @sniptest filename=filter_active_runs.py
# @sniptest show=9-19
# ruff: noqa: E402 -- fixture setup precedes the unchanged displayed import
import os

from notte_sdk import NotteClient as FixtureClient

function_id = os.environ["NOTTE_FUNCTION_ID"]
completed = FixtureClient().Function(function_id).run(url="https://example.com", stream=False)

from notte_sdk import NotteClient

client = NotteClient()

# Get only active runs
active_runs = client.functions.list_runs(function_id, only_active=True)

print(f"Active runs: {len(active_runs.items)}")

for run in active_runs.items:
    print(f"Run {run.workflow_run_id} - {run.status}")

history = client.functions.list_runs(function_id, only_active=False)
assert any(run.function_run_id == completed.function_run_id for run in history.items)
assert not active_runs.items
results = [run.status for run in active_runs.items]
