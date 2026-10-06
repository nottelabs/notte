# @sniptest filename=run_function.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id="d3c31289-f28b-49bd-a340-95e071cfef7e")
result = function.run(count="3")
print(result)
