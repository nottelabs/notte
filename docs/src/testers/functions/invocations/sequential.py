# @sniptest filename=sequential.py
# @sniptest show=7-14
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(function_id="func_abc123")
urls = ["https://example1.com", "https://example2.com"]

results = []
for url in urls:
    result = function.run(url=url)
    results.append(result.result)

print(results)
