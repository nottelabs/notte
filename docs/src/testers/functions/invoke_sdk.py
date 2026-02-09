# @sniptest filename=invoke_sdk.py
# @sniptest show=6-9
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id="func_abc123")

# Via SDK
result = function.run(url="https://example.com", search_query="laptop")

print(result.result)
