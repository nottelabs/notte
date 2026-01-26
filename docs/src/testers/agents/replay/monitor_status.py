# @sniptest filename=monitor_status.py
# @sniptest show=7-21
import time

from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.start(task="Long running task")

    while True:
        status = agent.status()

        if status.status == "closed":
            break

        print(f"Steps: {len(status.steps)}")

        # Get replay so far (if supported)
        # replay = agent.replay()
        # replay.show()

        time.sleep(5)
