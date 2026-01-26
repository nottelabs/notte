# @sniptest filename=check.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Check a checkbox
    session.execute(type="check", selector="input[type='checkbox']#terms", value=True)

    # Uncheck a checkbox
    session.execute(type="check", selector="input[type='checkbox']#newsletter", value=False)
