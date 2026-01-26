# @sniptest filename=handling_results.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="workflow_abc123")
result = function.run(url="https://example.com")

# Check status
if result.status == "closed":
    print("Success!")
    print(result.result)  # Function return value
elif result.status == "failed":
    print("Function failed")
    print(result.result)  # Error message

# Access metadata
print(f"Workflow ID: {result.workflow_id}")
print(f"Run ID: {result.workflow_run_id}")
print(f"Session ID: {result.session_id}")
