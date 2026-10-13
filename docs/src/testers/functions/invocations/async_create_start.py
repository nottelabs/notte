# @sniptest filename=async_create_start.py
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])
# Optional: create a run record when you need its ID before execution.
created = function.create_run()

run_id = created.function_run_id
print(f"Run created: {run_id}")

# Execute that run and wait for its result.
result = function.run(function_run_id=run_id, url="https://example.com")
print(result.result)
run = function.get_run(run_id)
print(run.status)
