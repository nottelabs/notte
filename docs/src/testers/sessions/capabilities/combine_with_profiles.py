# @sniptest filename=combine_with_profiles.py
from notte_sdk import NotteClient
from notte_sdk.types import ExternalProxy

client = NotteClient()

us_proxy = ExternalProxy(server="http://us-static.example.com:8080", username="user", password="pass")
eu_proxy = ExternalProxy(server="http://eu-static.example.com:8080", username="user", password="pass")

# Each profile has its own static IP and cookie file
with client.Session(proxies=[us_proxy], cookie_file="user1.json") as session:
    page = session.page
    page.goto("https://example.com")

with client.Session(proxies=[eu_proxy], cookie_file="user2.json") as session:
    page = session.page
    page.goto("https://example.com")
