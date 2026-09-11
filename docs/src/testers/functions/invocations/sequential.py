# @sniptest filename=sequential.py
# @sniptest show=9-15
import json
import os

from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(os.environ["NOTTE_FUNCTION_ID"])

urls = ["https://example.com", "https://example.org"]
results = []
for url in urls:
    result = function.run(url=url)
    results.append(result.result)

print(results)

print(json.dumps({"results": results}))
