# @sniptest filename=view_in_notebook.py
from IPython.display import Video
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

replay = session.replay()
# Display the MP4 inline in a Jupyter cell
Video(replay.mp4_url)
