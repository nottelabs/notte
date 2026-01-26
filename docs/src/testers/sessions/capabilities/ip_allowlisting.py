# @sniptest filename=ip_allowlisting.py
from notte_sdk import NotteClient
from notte_sdk.types import ExternalProxy, NotteProxy

client = NotteClient()

# Your server's IP is 203.0.113.1 and it's allowlisted
proxy = ExternalProxy(server="http://203.0.113.1:8080", username="user", password="pass")
proxies: list[NotteProxy | ExternalProxy] = [proxy]

with client.Session(proxies=proxies) as session:
    page = session.page
    page.goto("https://admin.example.com")
    # Access granted due to allowlisted IP
