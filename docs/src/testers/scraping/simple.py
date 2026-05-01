# @sniptest filename=simple_scrape.py
from notte_sdk import NotteClient

client = NotteClient()
markdown = client.scrape(
    url="https://www.notte.cc",
    only_main_content=True,
)
print(markdown)
