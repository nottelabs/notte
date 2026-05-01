# @sniptest filename=proxies_simple.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(proxies=True) as session:
    page = session.page
    page.goto("https://example.com")
