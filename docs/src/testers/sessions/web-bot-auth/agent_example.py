# @sniptest filename=agent_example.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(web_bot_auth=True) as session:
    agent = client.Agent(session=session)
    response = agent.run(task="Go to example.com and extract the main content")
    print(response.answer)
