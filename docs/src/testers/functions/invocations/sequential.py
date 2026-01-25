# @sniptest filename=sequential.py
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id="func_abc123")

results = []
for url in urls:
    result = function.run(url=url)
    results.append(result.result)

print(results)
