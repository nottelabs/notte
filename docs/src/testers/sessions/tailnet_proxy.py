# @sniptest filename=tailnet_proxy.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient
from notte_sdk.types import ProxySettings, TailnetProxy

client = NotteClient()

# Configure a Tailscale tsnet proxy using OAuth client credentials
tailnet_proxy = TailnetProxy(
    oauth_client_id="your-tailscale-oauth-client-id",
    oauth_client_secret="your-tailscale-oauth-client-secret",
)

# Start a session routed through your tailnet
proxies: list[ProxySettings] = [tailnet_proxy]
with client.Session(proxies=proxies) as session:
    _ = session.execute(type="goto", url="https://grafana.your-tailnet.ts.net/")
    _ = session.observe().screenshot.bytes()
