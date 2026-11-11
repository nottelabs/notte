# @sniptest filename=manage_schedule.py
# @sniptest show=6-32
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os

function_id = os.environ["NOTTE_FUNCTION_ID"]

from notte_sdk import NotteClient

client = NotteClient()

# Add a schedule. Times are UTC.
schedule = client.functions.add_schedule(
    function_id,
    cron="0 9 ? * * *",
    variables={"url": "https://example.com"},
)
try:
    # Change it in place: same schedule ID, new expression.
    client.functions.update_schedule(
        function_id,
        schedule.schedule_id,
        cron="0 18 ? * MON-FRI *",
        variables={"url": "https://example.com"},
    )

    # List every schedule of the function and their shared state.
    listed = client.functions.list_schedules(function_id)
    for item in listed.schedules:
        print(item.schedule_id, item.cron)
    print(listed.state)
finally:
    # Remove this schedule. The function's other schedules keep running.
    client.functions.remove_schedule(function_id, schedule.schedule_id)

crons = [item.cron for item in listed.schedules if item.schedule_id == schedule.schedule_id]
assert crons == ["0 18 ? * MON-FRI *"]
results = [crons == ["0 18 ? * MON-FRI *"]]
