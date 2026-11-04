# @sniptest filename=deletion_protection.py
# @sniptest show=6-16
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os

function_id = os.environ["NOTTE_FUNCTION_ID"]

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id=function_id)

# Protect the function: deletes are refused until this is turned off
function.set_deletion_protection(True)
print(function.response.deletion_protected)

# Turning it off takes the key of a workspace admin or owner
function.set_deletion_protection(False)

results = [function.response.deletion_protected is False]
