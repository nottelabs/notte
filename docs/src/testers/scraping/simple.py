# @sniptest filename=simple_scrape.py
# @sniptest show=1-8
from notte_sdk import NotteClient

client = NotteClient()
markdown = client.scrape(
    url="https://www.notte.cc",
    only_main_content=True,
)
print(markdown)

results = [isinstance(markdown, str), "notte" in markdown.lower()]
