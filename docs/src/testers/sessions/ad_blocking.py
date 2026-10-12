# @sniptest filename=ad_blocking.py
# @sniptest show=1-12
from notte_sdk import NotteClient

client = NotteClient()

# Ad blocking is on by default
with client.Session() as default_session:
    default_session.execute(type="goto", url="https://example.com")

# Turn it off when a site needs its ads or trackers to load
with client.Session(block_ads=False) as session:
    session.execute(type="goto", url="https://example.com")

results = [default_session.status().status, session.status().status]
