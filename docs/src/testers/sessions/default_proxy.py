# @sniptest filename=default_proxy.py
# @sniptest show=1-8
from notte_sdk import NotteClient

client = NotteClient()

# Start a session with built-in proxies
with client.Session(proxies=True) as session:
    _ = session.execute(type="goto", url="https://www.notte.cc/")
    _ = session.observe()

status = session.status()
assert status.proxies is True
