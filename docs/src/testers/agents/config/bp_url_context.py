# @sniptest filename=bp_url_context.py
# @sniptest show=6-10
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    # Good - start where needed
    agent.run(task="Extract product details", url="https://example.com/product/123")

    # Less efficient - agent must navigate first
    agent.run(task="Go to product page and extract details", url="https://example.com")
