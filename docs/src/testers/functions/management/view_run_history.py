# @sniptest filename=view_run_history.py
from notte_sdk import NotteClient

client = NotteClient()

# Get recent runs
runs = client.functions.list_runs(
    function_id="function_abc123",
    only_active=False,  # Include completed runs
)

for run in runs.items:
    print(f"Run ID: {run.workflow_run_id}")
    print(f"Status: {run.status}")
    print(f"Created: {run.created_at}")
    print(f"Updated: {run.updated_at}")
    print("---")
