# @sniptest filename=cloud_execution.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="workflow_abc123")
# Runs on Notte infrastructure
result = function.run(
    url="https://example.com",
    local=False,  # Default
)
