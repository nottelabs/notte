# @sniptest filename=agent_replay.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session, max_steps=10)
    result = agent.run(task="Find the contact email on example.com")

# Get agent replay directly
replay = agent.replay()
replay.save("agent_run.mp4")
