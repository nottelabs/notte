# @sniptest filename=consume_stream.py
# @sniptest typecheck_only=true
import json
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
    timeout=(10, 600),
)
response.raise_for_status()

# The thread ID lets you send follow-up turns later
thread_id = response.headers["x-thread-id"]
print("Thread ID:", thread_id)

for line in response.iter_lines():
    if not line:
        continue
    decoded = line.decode("utf-8")
    if not decoded.startswith("data: "):
        continue
    payload = decoded[len("data: ") :]
    if payload == "[DONE]":
        break
    chunk = json.loads(payload)
    print(chunk.get("type"), chunk)
