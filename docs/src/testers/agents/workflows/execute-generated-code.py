# Generated from agent
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")
    session.execute(type="click", selector="button.search")
    session.execute(type="fill", selector="input[name='query']", value="laptop")
    data = session.scrape(instructions="Extract product names")

print(data)
