from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Good - specific task
    with client.AgentFallback(session, task="Add the blue XL t-shirt to cart") as fb:
        session.execute(type="click", selector="#add-to-cart")

    # Less clear - vague task
    with client.AgentFallback(session, task="Do something") as fb:
        session.execute(type="click", selector="#button")
