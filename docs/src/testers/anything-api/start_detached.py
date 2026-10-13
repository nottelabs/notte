# @sniptest filename=start_detached.py
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
    json={"query": "fetch the top 3 hacker news posts", "detach": True},
    timeout=30,
)
response.raise_for_status()  # 202 Accepted

run = response.json()
print("Thread ID:", run["thread_id"])
print("Status:", run["status"])  # "started"
print("Follow along at:", run["url"])
