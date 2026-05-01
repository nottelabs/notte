# @sniptest filename=stop_running.py
# @sniptest show=6-8
from notte_sdk import NotteClient

client = NotteClient()
run_id = "run_xyz789"

# Stop a long-running function
client.functions.stop_run("function_abc123", run_id)
