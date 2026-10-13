# @sniptest filename=timeout_examples.py
# @sniptest show=6-15
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os

function_id = os.environ["NOTTE_FUNCTION_ID"]

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id=function_id)

# Stop waiting if the server sends nothing for 60 seconds (default: 300)
result = function.run(url="https://example.com", timeout=60)

# Tolerate longer quiet periods, e.g. long steps that log nothing
result = function.run(url="https://example.com", timeout=600)

assert result.status == "closed"
assert result.result == {"url": "https://example.com", "search_query": ""}
