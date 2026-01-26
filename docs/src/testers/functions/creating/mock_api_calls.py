# @sniptest filename=mock_api_calls.py
from notte_sdk import NotteClient

client = NotteClient()

# Load existing function with decryption key for local execution
function = client.Function(
    function_id="func_abc123",
    decryption_key="your-decryption-key",  # Required for local execution
)

# Run locally (not on cloud)
result = function.run(local=True, url="https://example.com")

print(result.result)
