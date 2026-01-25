from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    with client.AgentFallback(session, task="Click the submit button") as fb:
        # Try specific selector first (fast and cheap)
        session.execute(type="click", selector="button#submit-btn")

        # If selector changed, agent finds the button (slower but works)
