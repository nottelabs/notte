# @sniptest filename=view_in_notebook.py
# @sniptest show=6-9
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

    replay = agent.replay()
    replay.save("notebook_replay.mp4")
