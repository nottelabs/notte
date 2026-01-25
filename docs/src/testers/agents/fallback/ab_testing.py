from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    with client.AgentFallback(session, task="Click continue button") as fb:
        # Try variant A
        session.execute(type="click", selector="#continue-a")

        # If user got variant B, agent adapts
