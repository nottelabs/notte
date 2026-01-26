# @sniptest filename=batch_invocation.py
from concurrent.futures import ThreadPoolExecutor

from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="func_abc123")

urls = ["https://site1.com", "https://site2.com", "https://site3.com"]


def invoke_function(url):
    return function.run(url=url)


# Run in parallel
with ThreadPoolExecutor(max_workers=3) as executor:
    results = list(executor.map(invoke_function, urls))

for result in results:
    print(result.result)
