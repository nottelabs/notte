# @sniptest filename=tailnet_proxy.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient
from notte_sdk.types import ProxySettings, TailnetProxy

client = NotteClient()

# Uses the Tailscale OAuth client connected to your workspace in the console
tailnet_proxy = TailnetProxy()

# Start a session routed through your tailnet
proxies: list[ProxySettings] = [tailnet_proxy]
with client.Session(proxies=proxies) as session:
    result = session.execute(type="goto", url="https://grafana.your-tailnet.ts.net/")
    screenshot = session.observe().screenshot.bytes()
