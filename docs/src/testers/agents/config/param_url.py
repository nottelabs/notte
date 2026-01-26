# @sniptest filename=param_url.py
# @sniptest show=7
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Extract pricing information", url="https://example.com/products")
