# @sniptest filename=async_create_start.py
from notte_sdk import NotteClient

client = NotteClient()
# Create a run (returns immediately)
run_response = client.functions.create_run("function_abc123", local=False)

run_id = run_response.workflow_run_id
print(f"Run created: {run_id}")

# Start the run
client.functions.run(run_id, function_id="function_abc123", variables={"url": "https://example.com"})
