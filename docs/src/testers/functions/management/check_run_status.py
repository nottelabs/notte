# @sniptest filename=check_run_status.py
from notte_sdk import NotteClient

client = NotteClient()

# Get run details
run_status = client.functions.get_run("function_abc123", "run_xyz789")

print(f"Status: {run_status.status}")  # "active", "closed", "failed"
print(f"Result: {run_status.result}")
print(f"Session ID: {run_status.session_id}")
