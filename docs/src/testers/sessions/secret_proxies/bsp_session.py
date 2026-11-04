# @sniptest filename=bsp_session.py
# @sniptest typecheck_only=true
from pathlib import Path

from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy, ProxySettings, SecretProxy

client = NotteClient()

proxies: list[ProxySettings] = [
    # The session's exit for every host you do not list
    NotteProxy.from_country("us"),
    SecretProxy(
        # The TLS terminator in front of browser-secret-proxy
        server="https://browser-secret-proxy.example.com:443",
        # SECRET_PROXY_USERNAME and SECRET_PROXY_PASSWORD
        username="proxy-user",
        password="a-long-random-password",
        # The CA from step 2, never its key
        ca_certificate=Path("ca.pem").read_text(),
        # The same hosts as -hosts
        hosts=["api.example.com"],
    ),
]

with client.Session(proxies=proxies) as session:
    # The browser sends the stand-in; api.example.com receives the real value
    session.execute(type="goto", url="https://api.example.com/echo?token=tok_standin_123")
