from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    with client.AgentFallback(session, task="Click the popup close button") as fb:
        # Try clicking without waiting
        session.execute(type="click", selector=".popup-close")

        # If popup not loaded yet, agent waits and retries
