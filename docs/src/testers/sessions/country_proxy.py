# @sniptest filename=country_proxy.py
# @sniptest show=1-10
from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy

client = NotteClient()

# Shorthand: pass a country code
session = client.Session(proxies="fr")

# Equivalent explicit form
session = client.Session(proxies=[NotteProxy.from_country("fr")])

proxies = NotteProxy.from_country("fr")
assert proxies.country is not None
results = [proxies.type, proxies.country.value]
