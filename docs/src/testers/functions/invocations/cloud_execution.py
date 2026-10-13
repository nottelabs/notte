# @sniptest filename=cloud_execution.py
# @sniptest show=8-12
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

# Runs on Notte infrastructure
result = function.run(
    url="https://example.com",
    local=False,  # Default
)
