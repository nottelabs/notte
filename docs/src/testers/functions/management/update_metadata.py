# @sniptest filename=update_metadata.py
# @sniptest show=8-21
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os

function_id = os.environ["NOTTE_FUNCTION_ID"]
api_url = os.environ["NOTTE_API_URL"]
api_key = os.environ["NOTTE_API_KEY"]

import requests

endpoint = f"{api_url}/functions/{function_id}"
headers = {"Authorization": f"Bearer {api_key}"}
response = requests.patch(
    endpoint,
    headers=headers,
    json={"name": "Price monitor", "description": "Checks competitor prices"},
    timeout=30,
)
response.raise_for_status()
metadata = requests.get(endpoint, headers=headers, timeout=30)
metadata.raise_for_status()
print(metadata.json()["name"])

assert metadata.json()["name"] == "Price monitor"
results = [metadata.json()["name"] == "Price monitor"]
