# @sniptest filename=vgs_session.py
# @sniptest typecheck_only=true
from pathlib import Path

from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy, ProxySettings, SecretProxy

client = NotteClient()

proxies: list[ProxySettings] = [
    NotteProxy.from_country("us"),
    SecretProxy(
        server="https://tntXXXXXXXXX.sandbox.verygoodproxy.com:8443",
        username="YOUR_VGS_ACCESS_CREDENTIAL_USERNAME",
        password="YOUR_VGS_ACCESS_CREDENTIAL_PASSWORD",
        # The VGS certificate from your dashboard's "Code snippets" section
        ca_certificate=Path("sandbox.pem").read_text(),
        hosts=["api.stripe.com"],
    ),
]

with client.Session(proxies=proxies) as session:
    print(session.session_id)
