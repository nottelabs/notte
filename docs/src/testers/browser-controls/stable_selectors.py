# @sniptest filename=stable_selectors.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Good - uses ID (stable)
    session.execute(type="click", id="submit-btn")

    # Good - uses data attribute
    session.execute(type="click", selector="button[data-testid='submit']")

    # Avoid - fragile position-based
    session.execute(type="click", selector="div > div > button:nth-child(3)")
