# @sniptest filename=session.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    _ = session.observe(url="https://duckduckgo.com")
# Save the replay to a file
replay = session.replay()
replay.save("replay.mp4")
