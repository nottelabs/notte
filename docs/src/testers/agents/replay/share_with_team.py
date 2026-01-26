# @sniptest filename=share_with_team.py
# @sniptest show=6-12
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Feature test")

    replay = agent.replay()
    replay.save(f"feature_test_{agent.agent_id}.mp4")

    # Share file with team
    # Or share console link
    print(f"Console replay: https://console.notte.cc/agents/{agent.agent_id}")
