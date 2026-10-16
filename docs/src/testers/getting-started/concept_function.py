# @sniptest filename=concept_function.py
# @sniptest show=5-7
from notte_sdk import NotteClient

client = NotteClient()
# Load an existing function by ID
function = client.Function(function_id="func_abc123")
function.run(url="https://example.com")
