# @sniptest filename=http_client.py
# @sniptest typecheck_only=true
import os

import httpx

credential = (
    httpx.post(
        "https://api.notte.cc/proxies/gateway/credentials",
        headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
        json={"country": "us"},
    )
    .raise_for_status()
    .json()
)

# Every request made with this client exits from a residential IP in the US
with httpx.Client(proxy=credential["proxy_url_tls"]) as http:
    print(http.get("https://api.ipify.org").text)
