import time

from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError

client = NotteClient()

function = client.Function(function_id="func_abc123")


def invoke_with_retry(function, **variables):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return function.run(**variables)
        except NotteAPIError as e:
            if e.status_code == 429:
                wait_time = 2**attempt  # Exponential backoff
                time.sleep(wait_time)
            else:
                raise
    raise RuntimeError("Max retries exceeded")


result = invoke_with_retry(function, url="https://example.com")
