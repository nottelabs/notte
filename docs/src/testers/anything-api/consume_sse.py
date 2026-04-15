# @sniptest filename=consume_sse.py
# @sniptest typecheck_only=true
import os

import requests

NOTTE_API_KEY = os.environ["NOTTE_API_KEY"]

response = requests.post(
    "https://anything.notte.cc/api/anything/start",
    headers={
        "Authorization": f"Bearer {NOTTE_API_KEY}",
        "Content-Type": "application/json",
    },
    json={"query": "fetch the top 3 hacker news posts"},
    stream=True,
    timeout=(10, 300),
)
response.raise_for_status()

for line in response.iter_lines():
    if line:
        decoded = line.decode("utf-8")
        if decoded.startswith("data: "):
            import json

            event = json.loads(decoded[6:])
            print(event["type"], event)
            if event["type"] == "done":
                print("Function ID:", event.get("function_id"))
                print("Cost:", event.get("total_cost_usd"))
