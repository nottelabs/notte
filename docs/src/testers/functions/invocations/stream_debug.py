# @sniptest filename=stream_debug.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="function_abc123")

# Development - stream logs
result = function.run(url="https://example.com", stream=True)

# Production - no log output (still waits for the result)
result = function.run(url="https://example.com", stream=False)
