from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Increase max_steps
    agent = client.Agent(session=session, max_steps=30)

    # Or break task into smaller steps
    result1 = agent.run(task="Navigate to products page")
    result2 = agent.run(task="Search for laptops")
