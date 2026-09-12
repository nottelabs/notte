# @sniptest filename=get_function_details.py
# @sniptest show=5-17
# ruff: noqa: E402 -- live fixture precedes displayed import
import os

function_id = os.environ["NOTTE_FUNCTION_ID"]
from notte_sdk import NotteClient

client = NotteClient()

# Get function by ID
function = client.Function(function_id=function_id)

# Access function properties
print(f"Function ID: {function.function_id}")
print(f"Name: {function.response.name}")
print(f"Description: {function.response.description}")
print(f"Latest Version: {function.response.latest_version}")
print(f"Versions: {function.response.versions}")

assert function.function_id == function_id
assert function.response.latest_version in function.response.versions
results = [function.function_id == function_id, bool(function.response.versions)]
