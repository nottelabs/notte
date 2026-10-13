# @sniptest filename=country_proxy.py
# @sniptest show=1-11
from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy, ProxySettings

client = NotteClient()

# Shorthand: pass a country code
session = client.Session(proxies="fr")

# Equivalent explicit form
proxies: list[ProxySettings] = [NotteProxy.from_country("fr")]
session = client.Session(proxies=proxies)

proxy = NotteProxy.from_country("fr")
assert proxy.country is not None
results = [proxy.type, proxy.country.value]
