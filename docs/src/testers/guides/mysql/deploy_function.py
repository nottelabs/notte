# @sniptest filename=deploy_function.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient

client = NotteClient()
function = client.Function(
    path="scrape_function.py",
    name="Hourly scrape to MySQL",
)
print(function.function_id)
print(function.run(url="https://example.com", stream=False).result)
