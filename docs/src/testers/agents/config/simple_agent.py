# @sniptest filename=simple_agent.py
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Find contact email")
