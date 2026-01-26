# @sniptest filename=concept_function.py
# @sniptest show=5-7
from notte_sdk import NotteClient

client = NotteClient()
# Create a function from existing workflow
function = client.Function(function_id="workflow_abc123")
function.run(url="https://example.com")
