from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Scraping inside a fallback raises a ValueError
    try:
        with client.AgentFallback(session, task="Task") as fb:
            data = session.scrape()  # Not allowed
    except ValueError as e:
        print(f"Not supported: {e}")

    # raise_on_failure=True inside a fallback also raises a ValueError
    try:
        with client.AgentFallback(session, task="Task") as fb:
            session.execute(type="click", selector="#btn", raise_on_failure=True)  # Not allowed
    except ValueError as e:
        print(f"Not supported: {e}")
