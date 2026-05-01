from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Fill the email field")

    # Check what agent saw
    for step in result.steps:
        print(f"Action: {step['action']}")
        print(f"Reasoning: {step.get('reasoning', 'N/A')}")
