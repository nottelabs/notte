# @sniptest filename=run_parameters.py
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="func_abc123")
result = function.run(
    # Your function parameters (passed as variables)
    url="https://example.com",
    query="search term",
    # Execution options
    stream=True,  # Stream logs in real-time (default: True)
    timeout=300,  # Timeout in seconds (default: 300)
    raise_on_failure=True,  # Raise exception on failure (default: True)
)
