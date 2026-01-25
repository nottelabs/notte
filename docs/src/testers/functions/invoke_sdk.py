# @sniptest filename=invoke_sdk.py
# Via SDK
result = function.run(url="https://example.com", search_query="laptop")

print(result.result)
