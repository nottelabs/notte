# @sniptest filename=rotate_proxies.py
from notte_sdk import NotteClient

client = NotteClient()

# Session 1 with US proxy
with client.Session(proxies="us") as session:
    # automation
    pass

# Session 2 with UK proxy
with client.Session(proxies="gb") as session:
    # automation
    pass
