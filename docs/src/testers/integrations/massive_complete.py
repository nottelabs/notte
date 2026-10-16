# @sniptest filename=massive_complete.py
import os

from dotenv import load_dotenv
from notte_sdk import NotteClient
from notte_sdk.types import ExternalProxy, ProxySettings

load_dotenv()


def main():
    massive_username = os.getenv("MASSIVE_USERNAME")
    massive_password = os.getenv("MASSIVE_PASSWORD")

    client = NotteClient()

    # Configure Massive proxy with US targeting
    massive_proxy = ExternalProxy(
        server="http://network.joinmassive.com:65534",
        username=f"{massive_username}-country-US",
        password=massive_password,
    )

    # Create a session with Massive proxy
    proxies: list[ProxySettings] = [massive_proxy]
    with client.Session(proxies=proxies) as session:
        # Browse and scrape through the proxied session
        session.execute(type="goto", url="https://www.notte.cc/pricing")
        pricing = session.scrape(instructions="extract the pricing information")
        print(f"Pricing: {pricing}")


if __name__ == "__main__":
    main()
