# @sniptest filename=session.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    _ = session.observe(url="https://duckduckgo.com")
# Download the replay to a file
replay = session.replay()
replay.download("replay.mp4")
