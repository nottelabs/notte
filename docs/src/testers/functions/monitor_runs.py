# @sniptest filename=monitor_runs.py
import time

from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="func_abc123")

# Start run
result = function.run(
    url="https://example.com",
    stream=False,  # Don't stream logs
)

run_id = result.workflow_run_id

# Poll status
while True:
    status = client.functions.get_run("func_abc123", run_id)

    print(f"Status: {status.status}")

    if status.status in ["closed", "failed"]:
        print(f"Final result: {status.result}")
        break

    time.sleep(5)  # Check every 5 seconds
