# @sniptest filename=batch_invocation.py
# @sniptest show=6-26
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os

function_id = os.environ["NOTTE_FUNCTION_ID"]

from concurrent.futures import ThreadPoolExecutor

from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id=function_id)

urls = ["https://site1.com", "https://site2.com", "https://site3.com"]


def invoke_function(url):
    return function.run(url=url)


# Run in parallel
with ThreadPoolExecutor(max_workers=3) as executor:
    results = list(executor.map(invoke_function, urls))

for result in results:
    print(result.result)

assert all(result.status == "closed" for result in results)
assert [result.result for result in results] == [{"url": url, "search_query": ""} for url in urls]
assert len({result.function_run_id for result in results}) == len(urls)
results = [result.result for result in results]
