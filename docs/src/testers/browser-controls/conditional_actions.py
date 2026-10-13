# @sniptest filename=conditional_actions.py
# @sniptest show=1-16
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Check if element exists
    result = session.execute(type="click", selector="button.optional", raise_on_failure=False)

    if result.success:
        # Element was there and clicked
        session.execute(type="click", selector="button.next")
    else:
        # Element wasn't there, skip
        print("Optional button not found, continuing...")

assert result.success is False
status = session.status()
