# @sniptest filename=default_proxy.py
from notte_sdk import NotteClient

client = NotteClient()

# Start a session with built-in proxies
with client.Session(proxies=True) as session:
    _ = session.observe(url="https://www.notte.cc/")
