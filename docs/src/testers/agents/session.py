# @sniptest filename=firefox.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(browser_type="firefox") as session:
    _ = client.Agent(session=session).run(
        task="What's the weather like in SF tonight?",
    )
