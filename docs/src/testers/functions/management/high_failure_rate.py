# @sniptest filename=high_failure_rate.py
# @sniptest show=14-29
# ruff: noqa: E402 -- hidden live fixture precedes displayed import
import os

from notte_sdk import NotteClient as FixtureClient

function_id = os.environ["NOTTE_FUNCTION_ID"]
failed = (
    FixtureClient()
    .Function(function_id)
    .run(url="https://example.com", fail=True, raise_on_failure=False, stream=False)
)
assert failed.status == "failed"

from notte_sdk import NotteClient

client = NotteClient()

runs = client.functions.list_runs(function_id, only_active=False)

failures = [r for r in runs.items if r.status == "failed"]

print(f"Failed runs: {len(failures)}/{len(runs.items)}")

# Analyze failure reasons
for run in failures[:5]:  # Last 5 failures
    run_detail = client.functions.get_run(function_id, run.function_run_id)
    print(f"Run {run.workflow_run_id}:")
    print(f"  Error: {run_detail.result}")
    print(f"  Time: {run.created_at}")

matched = [run for run in failures[:5] if run.function_run_id == failed.function_run_id]
assert len(matched) == 1
owned_detail = client.functions.get_run(function_id, failed.function_run_id)
assert "Example function failure" in str(owned_detail.result)
results = [matched[0].status, "Example function failure" in str(owned_detail.result)]
