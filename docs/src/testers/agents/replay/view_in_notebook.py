# @sniptest filename=view_in_notebook.py
# @sniptest show=4-11
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

replay = session.replay()
replay.download("notebook_replay.mp4")
