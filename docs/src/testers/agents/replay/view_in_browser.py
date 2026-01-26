# @sniptest filename=view_in_browser.py
# @sniptest show=6-9
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complete task")

    # Get replay URL
    print(f"View replay: https://console.notte.cc/agents/{result.agent_id}/replay")
