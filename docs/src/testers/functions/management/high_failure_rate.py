# @sniptest filename=high_failure_rate.py
from notte_sdk import NotteClient

client = NotteClient()

runs = client.functions.list_runs("function_abc123")

failures = [r for r in runs.items if r.status == "failed"]

print(f"Failed runs: {len(failures)}/{len(runs.items)}")

# Analyze failure reasons
for run in failures[:5]:  # Last 5 failures
    print(f"Run {run.workflow_run_id}:")
    print(f"  Error: {run.result}")
    print(f"  Time: {run.created_at}")
