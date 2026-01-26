# @sniptest filename=get_function_details.py
from notte_sdk import NotteClient

client = NotteClient()

# Get function by ID
function = client.Function(function_id="func_abc123")

# Access function properties
print(f"Function ID: {function.function_id}")
print(f"Name: {function.response.name}")
print(f"Description: {function.response.description}")
print(f"Latest Version: {function.response.latest_version}")
print(f"Versions: {function.response.versions}")
