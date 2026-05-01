# @sniptest filename=session_based.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Navigate and authenticate
    session.execute(type="goto", url="https://example.com/login")
    session.execute(type="fill", selector="input[name='email']", value="user@example.com")
    session.execute(type="fill", selector="input[name='password']", value="password")
    session.execute(type="click", selector="button[type='submit']")

    # Navigate to protected page
    session.execute(type="goto", url="https://example.com/dashboard")

    # Scrape the page
    content = session.scrape()
