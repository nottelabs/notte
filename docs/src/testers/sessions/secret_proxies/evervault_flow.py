# @sniptest filename=evervault_flow.py
# @sniptest typecheck_only=true
import os

import httpx
from notte_sdk import NotteClient
from notte_sdk.types import NotteProxy, ProxyGeolocationCountry, ProxySettings, SecretProxy

STICKY_SESSION = "checkout-4821"

# 1. Mint a Notte gateway credential pinned to one residential exit
gateway = httpx.post(
    "https://api.notte.cc/proxies/gateway/credentials",
    headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
    json={"country": "us", "sticky_session": STICKY_SESSION},
).json()

# 2. Create Browser Tokens; Evervault's egress goes through Notte's gateway
tokens = httpx.post(
    "https://api.evervault.com/browser-tokens",
    auth=(os.environ["EVERVAULT_APP_ID"], os.environ["EVERVAULT_API_KEY"]),
    json={
        "data": [
            {"category": "card.number", "value": "ev:encrypted:...", "id": "card-number"},
            {"category": "card.cvv", "value": "ev:encrypted:...", "id": "card-cvv"},
        ],
        "permissions": [{"action": "decrypt", "target": "api.stripe.com"}],
        "ttl": 900,
        "proxySettings": {
            "type": "custom",
            "scheme": "https",
            "hostname": "proxy.notte.cc",
            "port": 443,
            "username": gateway["username"],
            "password": gateway["password"],
        },
    },
).json()
relay = tokens["proxyConfiguration"]

# 3. Start the session: same sticky_session and country, Evervault's relay for the listed host
proxies: list[ProxySettings] = [
    NotteProxy(country=ProxyGeolocationCountry.UNITED_STATES, sticky_session=STICKY_SESSION),
    SecretProxy(
        server=f"https://{relay['hostname']}:{relay['port']}",
        username=relay["username"],
        password=relay["password"],
        ca_certificate=httpx.get("https://ca.evervault.com").text,
        hosts=["api.stripe.com"],
    ),
]

client = NotteClient()
with client.Session(proxies=proxies) as session:
    # 4. The stand-in values the agent types
    stand_ins = {item["id"]: item["value"] for item in tokens["data"]}
    print(session.session_id, stand_ins)
