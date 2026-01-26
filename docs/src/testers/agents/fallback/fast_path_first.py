from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    with client.AgentFallback(session, task="Navigate to dashboard") as fb:
        # Fast path - direct click
        session.execute(type="click", selector="a[href='/dashboard']")

        # Agent only invoked if fast path fails
