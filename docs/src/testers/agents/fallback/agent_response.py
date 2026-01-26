from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    with client.AgentFallback(session, task="Extract data") as fb:
        session.execute(type="click", selector="#button")

    if fb.agent_invoked and fb.agent_response:
        print(f"Agent answer: {fb.agent_response.answer}")
        print(f"Agent steps: {len(fb.agent_response.steps)}")
