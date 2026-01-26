# @sniptest filename=geographic_targeting.py
from notte_sdk import NotteClient
from notte_sdk.types import ExternalProxy, NotteProxy

client = NotteClient()

# US static IP
us_proxy = ExternalProxy(server="http://us-static.example.com:8080", username="user", password="pass")

# EU static IP
eu_proxy = ExternalProxy(server="http://eu-static.example.com:8080", username="user", password="pass")

# Access region-specific content
proxies: list[NotteProxy | ExternalProxy] = [us_proxy]
with client.Session(proxies=proxies) as session:
    page = session.page
    page.goto("https://us.example.com")
