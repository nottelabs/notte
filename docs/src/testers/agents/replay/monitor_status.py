# @sniptest filename=monitor_status.py
# @sniptest show=6-22
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

        time.sleep(5)

# Get replay after completion
# replay = session.replay()
# replay.download("replay.mp4")
