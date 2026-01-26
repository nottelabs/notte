# @sniptest filename=use_variables.py
# @sniptest show=9-13
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id="func_abc123")
dynamic_url = "https://example.com"
user_input = "search query"

# Good - parameterized
result = function.run(url=dynamic_url, query=user_input)

# Bad - hardcoded
result = function.run()  # URL hardcoded in function
