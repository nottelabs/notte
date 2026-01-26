# @sniptest filename=custom_proxy.py
from notte_sdk import NotteClient
from notte_sdk.types import ExternalProxy, NotteProxy

client = NotteClient()

# Configure custom proxy settings
proxy_settings = ExternalProxy(
    server="http://your-proxy-server:port",
    username="your-username",
    password="your-password",
)

# Start a session with custom proxy
proxies: list[NotteProxy | ExternalProxy] = [proxy_settings]
with client.Session(proxies=proxies) as session:
    # use your session
    pass
