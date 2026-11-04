# @sniptest filename=shared_exit_session.py
# @sniptest typecheck_only=true
from pathlib import Path

from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy, ProxyGeolocationCountry, ProxySettings, SecretProxy

client = NotteClient()

proxies: list[ProxySettings] = [
    # Same sticky_session and country as the gateway credential
    NotteProxy(country=ProxyGeolocationCountry.UNITED_STATES, sticky_session="checkout-4821"),
    SecretProxy(
        server="https://secret-proxy.example.com:443",
        username="YOUR_PROXY_USERNAME",
        password="YOUR_PROXY_PASSWORD",
        ca_certificate=Path("your-ca.pem").read_text(),
        hosts=["api.stripe.com"],
    ),
]

with client.Session(proxies=proxies) as session:
    print(session.session_id)
