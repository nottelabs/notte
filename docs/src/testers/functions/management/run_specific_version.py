# @sniptest filename=rollback_version.py
import requests
from notte_sdk import NotteClient

client = NotteClient()

function = client.Function(function_id="func_abc123")

# Cloud runs always execute the latest version
result = function.run(url="https://example.com")

# To go back to an older version, roll back to it: its code is redeployed
# as a new latest version
print(function.response.versions)

response = requests.post(
    f"https://api.notte.cc/functions/{function.function_id}/rollback",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"version": function.response.versions[0]},
)
response.raise_for_status()
print(response.json()["latest_version"])
