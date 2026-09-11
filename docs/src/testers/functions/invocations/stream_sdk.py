# @sniptest filename=stream_sdk.py
# @sniptest show=8-12
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

# Stream logs while running
result = function.run(
    url="https://example.com",
    stream=True,  # Logs printed to console
)
