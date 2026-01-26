# @sniptest filename=review_failed_agents.py
# @sniptest show=6-11
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Critical task")

    if not result.success:
        replay = agent.replay()
        replay.save(f"failure_{agent.agent_id}.mp4")
        print(f"Saved replay for debugging: failure_{agent.agent_id}.mp4")
