# @sniptest filename=watch_replay.py
# @sniptest show=6-12
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Complete task")

    replay = agent.replay()
    replay.save("debug_replay.mp4")

    # Watch where it failed
    # Identify if element selectors were wrong
    # Check if page loaded correctly
