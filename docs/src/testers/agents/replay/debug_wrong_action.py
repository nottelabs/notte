from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Fill the email field")

    # Check what the agent saw and decided at each step
    for step in result.steps:
        if step["type"] != "agent_completion":
            continue
        completion = step["value"]
        print(f"Page summary: {completion['state']['page_summary']}")
        print(f"Next goal: {completion['state']['next_goal']}")
        print(f"Action: {completion['action']}")
