# @sniptest filename=invoke_sdk.py
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id=os.environ["NOTTE_FUNCTION_ID"])

# Via SDK
result = function.run(url="https://example.com", search_query="laptop")

print(result.result)
