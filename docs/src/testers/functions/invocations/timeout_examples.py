# @sniptest filename=timeout_examples.py
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id="function_abc123")

# Short task
result = function.run(url="https://example.com", timeout=60)

# Long task
result = function.run(url="https://example.com", timeout=600)
