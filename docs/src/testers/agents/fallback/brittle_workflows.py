from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Good use case - page layout changes often
    with client.AgentFallback(session, task="Click pricing link") as fb:
        session.execute(type="click", selector="a[href='/pricing']")
