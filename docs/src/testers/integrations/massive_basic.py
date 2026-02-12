# @sniptest filename=massive_basic.py
from notte_sdk import NotteClient
from notte_sdk.types import ExternalProxy

client = NotteClient()

# Configure Massive proxy
massive_proxy = ExternalProxy(
    server="http://network.joinmassive.com:65534",
    username="your-username",
    password="your-password",
)

# Create a session routed through Massive
with client.Session(proxies=[massive_proxy]) as session:
    session.observe(url="https://example.com")
