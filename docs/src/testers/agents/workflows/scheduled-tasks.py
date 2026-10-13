# @sniptest filename=scheduled-tasks.py
# @sniptest show=6-14
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # Manual run to figure out the task
    agent = client.Agent(session=session)
    result = agent.run(task="Extract daily price changes")

    # Convert to function
    function = agent.workflow.create_function()

    # Schedule it to run daily: see Function Schedules
    print(f"Function ID to schedule: {function.function_id}")
