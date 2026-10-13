# @sniptest filename=invoke_function.py
# @sniptest show=6-18
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os

function_id = os.environ["NOTTE_FUNCTION_ID"]

from notte_sdk import NotteClient

client = NotteClient()

# Get function by ID
function = client.Function(function_id=function_id)

# Run function with parameters
result = function.run(url="https://example.com", search_query="laptop")

print(result.result)  # Access the return value
print(result.status)  # "closed" or "failed"
print(result.session_id)  # Session ID if created

assert result.function_id == function_id
