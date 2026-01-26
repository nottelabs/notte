# @sniptest filename=stop_running.py
from notte_sdk import NotteClient

client = NotteClient()

# Stop specific run
client.functions.stop_run("function_abc123", "run_xyz789")

print("Function execution stopped")
