# @sniptest filename=external_cdp.py
from notte_sdk import NotteClient

client = NotteClient()
cdp_url = "wss://your-external-cdp-url"

with client.Session(cdp_url=cdp_url) as session:
    agent = client.Agent(session=session, max_steps=5)
    agent.run(task="extract pricing plans from https://www.notte.cc/")
