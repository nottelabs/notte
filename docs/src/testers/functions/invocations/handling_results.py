# @sniptest filename=handling_results.py
# @sniptest show=8-21
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

result = function.run(url="https://example.com")

# Check status
if result.status == "closed":
    print("Success!")
    print(result.result)  # Function return value
elif result.status == "failed":
    print("Function failed")
    print(result.result)  # Error message

# Access metadata
print(f"Function ID: {result.function_id}")
print(f"Run ID: {result.function_run_id}")
print(f"Session ID: {result.session_id}")
