# @sniptest filename=view_run_history.py
# @sniptest show=9-24
# ruff: noqa: E402 -- hidden live fixture precedes displayed import
import os

from notte_sdk import NotteClient as FixtureClient

function_id = os.environ["NOTTE_FUNCTION_ID"]
completed = FixtureClient().Function(function_id).run(url="https://example.com", stream=False)

from notte_sdk import NotteClient

client = NotteClient()

# Get recent runs
runs = client.functions.list_runs(
    function_id=function_id,
    only_active=False,  # Include completed runs
)

for run in runs.items:
    print(f"Run ID: {run.workflow_run_id}")
    print(f"Status: {run.status}")
    print(f"Created: {run.created_at}")
    print(f"Updated: {run.updated_at}")
    print("---")

matched = [run for run in runs.items if run.function_run_id == completed.function_run_id]
assert len(matched) == 1
assert matched[0].status == "closed"
results = [run.status for run in matched]
