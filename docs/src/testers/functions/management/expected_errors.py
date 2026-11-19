# @sniptest filename=expected_errors.py
# @sniptest show=6-15
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os

function_id = os.environ["NOTTE_FUNCTION_ID"]

from notte_sdk import NotteClient

client = NotteClient()

# Runs that raise these classes, or a subclass of them, end as "rejected"
function = client.functions.metadata_update(function_id, expected_errors=["AccountNotUnique", "StaffReviewRequired"])
print(function.expected_errors)

# An empty list turns it off again
cleared = client.functions.metadata_update(function_id, expected_errors=[])

results = [function.expected_errors, cleared.expected_errors]
