# @sniptest filename=agent_quickstart.py

from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=10)

    result = agent.run(task="Go to example.com and find the contact email")

    print(result.answer)
