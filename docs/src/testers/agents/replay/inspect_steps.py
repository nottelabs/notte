from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complete task")

    for i, step in enumerate(result.steps):
        print(f"Step {i + 1}: {step['action']}")
        print(f"  Success: {step['success']}")
        if not step['success']:
            print(f"  Error: {step['message']}")
