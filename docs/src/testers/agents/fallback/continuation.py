from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    with client.AgentFallback(session, task="Complete checkout") as fb:
        session.execute(type="click", selector="#step1")  # Success
        session.execute(type="click", selector="#step2")  # Fails - agent spawned
        session.execute(type="click", selector="#step3")  # Skipped (agent already handled task)
