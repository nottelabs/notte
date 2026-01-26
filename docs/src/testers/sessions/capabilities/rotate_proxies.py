# @sniptest filename=rotate_proxies.py
from notte_sdk import NotteClient
from notte_sdk.types import ProxyGeolocationCountry

client = NotteClient()

# Session 1 with US proxy
with client.Session(proxies=ProxyGeolocationCountry.UNITED_STATES) as session:
    # automation
    pass

# Session 2 with UK proxy
with client.Session(proxies=ProxyGeolocationCountry.UNITED_KINGDOM) as session:
    # automation
    pass
