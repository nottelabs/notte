import os

import requests
from notte_sdk import NotteClient
from pydantic import BaseModel


class Articles(BaseModel):
    titles: list[str]


client = NotteClient()
BROWSERBASE_API_KEY = os.environ["BROWSERBASE_API_KEY"]

# Create session on BrowserBase (using their API)
browserbase_response = requests.post(
    "https://api.browserbase.com/v1/sessions",
    headers={"X-BB-API-Key": BROWSERBASE_API_KEY},
    json={"projectId": "your-project-id"},
)

session_data = browserbase_response.json()
cdp_url = session_data["connectUrl"]

# Connect Notte to BrowserBase
with client.Session(cdp_url=cdp_url) as session:
    page = session.page
    page.goto("https://example.com")

    # Use Notte's scraping
    result = session.scrape(instructions="Get all article titles", response_format=Articles)

    print(result)

# Without keepAlive, BrowserBase releases its session once the CDP connection closes
