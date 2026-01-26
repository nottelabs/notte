# @sniptest filename=filter_active_runs.py
from notte_sdk import NotteClient

client = NotteClient()

# Get only active runs
active_runs = client.functions.list_runs("function_abc123", only_active=True)

print(f"Active runs: {len(active_runs.items)}")

for run in active_runs.items:
    print(f"Run {run.workflow_run_id} - {run.status}")
