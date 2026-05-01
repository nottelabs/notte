# @sniptest filename=sdk_error_handling.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="workflow_abc123")

try:
    result = function.run(url="https://example.com")

    if result.status == "failed":
        print(f"Function failed: {result.result}")

except Exception as e:
    print(f"Unexpected error: {e}")
