# @sniptest filename=fill.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Fill by selector
    session.execute(type="fill", selector="input[name='email']", value="user@example.com")

    # Fill by ID from observe()
    session.execute(type="fill", id="I1", value="user@example.com")

    # Fill by placeholder selector
    session.execute(type="fill", selector="input[placeholder='Enter your email']", value="user@example.com")
