# @sniptest filename=delete_function.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="func_abc123")

# Delete function
function.delete()

print("Function deleted")
