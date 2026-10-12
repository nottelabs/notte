from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    with client.AgentFallback(
        session,
        task="Complete signup",
        max_steps=15,  # Agent parameters
        reasoning_model="anthropic/claude-sonnet-4-5-20250929",
        use_vision=True,
    ) as fb:
        session.execute(type="click", selector="#signup")
