# @sniptest filename=price_monitor.py
# @sniptest show=5-20
from notte_sdk import NotteClient

client = NotteClient()


# price_monitor.py
def run(product_urls: list[str]):
    run_client = NotteClient()
    prices = []

    for url in product_urls:
        with run_client.Session() as session:
            session.execute(type="goto", url=url)
            price = session.scrape(instructions="Extract product price")
            prices.append({"url": url, "price": price})

    return prices


# Deploy and schedule to run daily
function = client.Function(path="price_monitor.py", name="Daily Price Monitor")

# Schedule via console: every day at 9 AM
