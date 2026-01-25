# @sniptest filename=run_specific_version.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="func_abc123")

# Run latest version (default)
result = function.run(url="https://example.com")

# Run specific version
result = function.run(url="https://example.com", version="v2")
