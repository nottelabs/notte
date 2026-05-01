# @sniptest filename=combine_with_profiles.py
from notte_sdk import NotteClient
from notte_sdk.types import ExternalProxy, NotteProxy

client = NotteClient()

us_proxy = ExternalProxy(server="http://us-static.example.com:8080", username="user", password="pass")
eu_proxy = ExternalProxy(server="http://eu-static.example.com:8080", username="user", password="pass")

# Each profile has its own static IP and cookie file
us_proxies: list[NotteProxy | ExternalProxy] = [us_proxy]
with client.Session(proxies=us_proxies, cookie_file="user1.json") as session:
    page = session.page
    page.goto("https://example.com")

eu_proxies: list[NotteProxy | ExternalProxy] = [eu_proxy]
with client.Session(proxies=eu_proxies, cookie_file="user2.json") as session:
    page = session.page
    page.goto("https://example.com")
