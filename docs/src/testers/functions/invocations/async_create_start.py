# @sniptest filename=async_create_start.py
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function("function_abc123")
# Create a run record without starting execution.
created = function.create_run()

run_id = created.function_run_id
print(f"Run created: {run_id}")

# Execute that run and wait for its result.
result = function.run(function_run_id=run_id, url="https://example.com")
