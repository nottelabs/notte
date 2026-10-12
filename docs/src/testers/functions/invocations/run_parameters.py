# @sniptest filename=run_parameters.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="workflow_abc123")
result = function.run(
    # Your function parameters (passed as variables)
    url="https://example.com",
    query="search term",
    # Execution options
    stream=True,  # Stream logs in real-time (default: True)
    timeout=300,  # Seconds without data from the server before giving up (default: 300)
    raise_on_failure=True,  # Raise exception on failure (default: True)
    local=False,  # Run locally vs cloud (default: False)
)
