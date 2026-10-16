# @sniptest filename=manage_schedule.py
# @sniptest show=8-31
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os

function_id = os.environ["NOTTE_FUNCTION_ID"]
api_url = os.environ["NOTTE_API_URL"]
api_key = os.environ["NOTTE_API_KEY"]

import requests

endpoint = f"{api_url}/functions/{function_id}"
headers = {"Authorization": f"Bearer {api_key}"}

try:
    # Create or replace the schedule. Times are UTC.
    response = requests.post(
        f"{endpoint}/schedule",
        headers=headers,
        json={"cron": "0 9 ? * * *", "variables": {"url": "https://example.com"}},
        timeout=30,
    )
    response.raise_for_status()

    # Read the schedule from the function metadata.
    metadata = requests.get(endpoint, headers=headers, timeout=30)
    metadata.raise_for_status()
    schedule = metadata.json()
    print(schedule["schedule_cron"], schedule["schedule_state"])
finally:
    # Delete the schedule when it is no longer needed.
    deleted = requests.delete(f"{endpoint}/schedule", headers=headers, timeout=30)
    deleted.raise_for_status()

assert schedule["schedule_cron"] == "0 9 ? * * *"
results = [schedule["schedule_cron"] == "0 9 ? * * *"]
