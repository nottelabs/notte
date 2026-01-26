# @sniptest filename=search_extract.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")
    session.execute(type="fill", selector="input[name='search']", value="laptop")
    session.execute(type="press_key", key="Enter")
    session.execute(type="wait", time_ms=2000)

    results = session.scrape(instructions="Extract search results")
    print(results)
