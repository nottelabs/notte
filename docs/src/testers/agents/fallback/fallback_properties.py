from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    with client.AgentFallback(session, task="Complete task") as fb:
        # Execute actions
        session.execute(type="click", selector="#button")

    # Check what happened
    print(f"All succeeded: {fb.success}")
    print(f"Agent was invoked: {fb.agent_invoked}")

    if fb.agent_response:
        print(f"Agent result: {fb.agent_response}")
