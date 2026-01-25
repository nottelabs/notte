# @sniptest filename=agent.py
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    results = agent.run(task="go to duckduckgo")
# Save the replay to a file
replay = agent.replay()
replay.save("replay.mp4")
