# @sniptest filename=country_proxy.py
# @sniptest show=1-3
from notte_sdk.types import NotteProxy

proxies = NotteProxy.from_country("fr")

results = [proxies.type, proxies.country.value]
