# @sniptest filename=version_management.py
# @sniptest show=6-16
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os

function_id = os.environ["NOTTE_FUNCTION_ID"]

from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id=function_id)

# Get all versions
print(f"Available versions: {function.response.versions}")

# Get latest version
print(f"Latest: {function.response.latest_version}")

assert function.response.function_id == function_id
results = [bool(function.response.versions), function.response.latest_version in function.response.versions]
