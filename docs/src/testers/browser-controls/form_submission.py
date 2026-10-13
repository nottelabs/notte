# @sniptest filename=form_submission.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com/contact")
    session.execute(type="fill", selector="#name", value="John Doe")
    session.execute(type="fill", selector="#email", value="john@example.com")
    session.execute(type="fill", selector="#message", value="Hello!")
    session.execute(type="click", selector="button[type='submit']")
