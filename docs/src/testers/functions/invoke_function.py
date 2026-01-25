# @sniptest filename=invoke_function.py
from notte_sdk import NotteClient

client = NotteClient()

# Get function by ID
function = client.Function(function_id="func_abc123")

# Run function with parameters
result = function.run(url="https://example.com", search_query="laptop")

print(result.result)  # Access the return value
print(result.status)  # "closed" or "failed"
print(result.session_id)  # Session ID if created
