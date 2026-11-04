# @sniptest filename=login_session.py
# @sniptest typecheck_only=true
from pathlib import Path

from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy, ProxySettings, SecretProxy

client = NotteClient()

# Stand-ins from your provider or your own proxy. They are not secrets:
# the page, the agent, screenshots and network logs only contain these values.
USERNAME = "tok_user_7Hq2Xc"
PASSWORD = "tok_pwd_9Kd3Wm"
OTP = "tok_otp_4Lm8Rv"

proxies: list[ProxySettings] = [
    NotteProxy.from_country("us"),
    SecretProxy(
        server="https://secret-proxy.example.com:443",
        username="YOUR_PROXY_USERNAME",
        password="YOUR_PROXY_PASSWORD",
        ca_certificate=Path("your-ca.pem").read_text(),
        # The host that receives the login and 2FA requests, not the app's host
        hosts=["auth.example.com"],
    ),
]

with client.Session(proxies=proxies) as session:
    session.execute(type="goto", url="https://app.example.com/login")

    # The form posts to auth.example.com, where your proxy swaps the stand-ins
    session.execute(type="fill", selector="input[name='username']", value=USERNAME)
    session.execute(type="fill", selector="input[name='password']", value=PASSWORD)
    session.execute(type="click", selector="button[type='submit']")

    # 2FA step: the same stand-in every time; your proxy sends the current code
    session.execute(type="fill", selector="input[name='otp']", value=OTP)
    session.execute(type="click", selector="button[type='submit']")
