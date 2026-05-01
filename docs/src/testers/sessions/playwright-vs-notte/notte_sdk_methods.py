# @sniptest filename=notte_sdk_methods.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")
    actions = session.observe(instructions="Fill the email input")
    session.execute(actions[0])  # Execute the action the AI recommends
    data = session.scrape(instructions="Extract all product names")
