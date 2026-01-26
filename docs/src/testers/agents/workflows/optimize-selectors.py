# @sniptest filename=optimize-selectors.py
# @sniptest show=6-10
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # Generated code might use:
    session.execute(type="click", selector="div.container > button:nth-child(3)")

    # Optimize to:
    session.execute(type="click", selector="button[data-testid='submit']")
