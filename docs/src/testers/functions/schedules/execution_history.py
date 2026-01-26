# @sniptest filename=execution_history.py
from notte_sdk import NotteClient

client = NotteClient()

# List recent runs
runs = client.functions.list_runs(
    "function_abc123",
    only_active=False,  # Include completed runs
)

for run in runs.items:
    print(f"Run {run.workflow_run_id}:")
    print(f"  Status: {run.status}")
    print(f"  Created: {run.created_at}")
    print(f"  Updated: {run.updated_at}")
