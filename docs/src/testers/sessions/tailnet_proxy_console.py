# @sniptest filename=tailnet_proxy_console.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient
from notte_sdk.types import ProxySettings, TailnetProxy

client = NotteClient()

# No credentials: uses the Tailscale OAuth client connected to your workspace
tailnet_proxy = TailnetProxy()

# Start a session routed through your tailnet
proxies: list[ProxySettings] = [tailnet_proxy]
with client.Session(proxies=proxies) as session:
    result = session.execute(type="goto", url="https://grafana.your-tailnet.ts.net/")
    screenshot = session.observe().screenshot.bytes()
