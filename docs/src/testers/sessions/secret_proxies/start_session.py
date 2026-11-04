# @sniptest filename=start_session.py
# @sniptest typecheck_only=true
from pathlib import Path

from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy, ProxySettings, SecretProxy

client = NotteClient()

proxies: list[ProxySettings] = [
    # The session's exit for every host you do not list
    NotteProxy.from_country("us"),
    # Your secret proxy, for the listed hosts only
    SecretProxy(
        server="https://secret-proxy.example.com:443",
        username="YOUR_PROXY_USERNAME",
        password="YOUR_PROXY_PASSWORD",
        ca_certificate=Path("your-ca.pem").read_text(),
        hosts=["api.stripe.com", "*.adyen.com"],
    ),
]

with client.Session(proxies=proxies) as session:
    # Server, hosts and CA fingerprints; never the credentials or the certificate
    assert session.response is not None
    summary = session.response.secret_proxy
    if summary is not None:
        print(summary.server, summary.hosts, summary.ca_sha256)
