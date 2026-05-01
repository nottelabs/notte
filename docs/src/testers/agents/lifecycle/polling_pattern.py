# @sniptest filename=polling_pattern.py
import time

from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    agent.start(task="Long task")

    while True:
        status = agent.status()

        if status.status == "closed":
            break

        print(f"Progress: {len(status.steps)} steps completed")
        time.sleep(5)  # Check every 5 seconds

    print(f"Final result: {status.answer}")
