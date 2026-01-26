# @sniptest filename=update_code.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="func_abc123")

# Update with new code
function.update(path="updated_function.py")

print(f"Updated to version: {function.response.latest_version}")
