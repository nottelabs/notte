# @sniptest filename=rate_limiting.py
import time

from notte_sdk import NotteClient
from notte_sdk.types import ExternalProxy, NotteProxy

client = NotteClient()

ip_pool: list[NotteProxy | ExternalProxy] = [
    ExternalProxy(server="http://ip1.example.com:8080", username="user", password="pass"),
    ExternalProxy(server="http://ip2.example.com:8080", username="user", password="pass"),
    ExternalProxy(server="http://ip3.example.com:8080", username="user", password="pass"),
]

for ip_proxy in ip_pool:
    proxies: list[NotteProxy | ExternalProxy] = [ip_proxy]
    with client.Session(proxies=proxies) as session:
        page = session.page
        page.goto("https://api.example.com/data")
        # Each IP has its own rate limit
    time.sleep(1)
