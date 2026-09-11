# @sniptest filename=stop_running.py
# @sniptest show=8-10
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function("function_abc123")
run_id = "run_xyz789"

# Stop a long-running function
function.stop_run(run_id)
