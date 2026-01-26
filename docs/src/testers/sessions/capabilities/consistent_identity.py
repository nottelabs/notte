# @sniptest filename=consistent_identity.py
from notte_sdk import NotteClient
from notte_sdk.types import ExternalProxy, NotteProxy

client = NotteClient()

static_proxy = ExternalProxy(server="http://static-ip.example.com:8080", username="user", password="pass")
proxies: list[NotteProxy | ExternalProxy] = [static_proxy]

# Day 1: Setup account
with client.Session(proxies=proxies, cookie_file="account.json") as session:
    page = session.page
    page.goto("https://example.com/register")
    # Register account

# Day 2: Use account (same IP)
with client.Session(proxies=proxies, cookie_file="account.json") as session:
    page = session.page
    page.goto("https://example.com/dashboard")
    # Account recognizes same IP + cookies
