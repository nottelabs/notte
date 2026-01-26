# @sniptest filename=error_handling.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Don't raise on failure
    result = session.execute(type="click", selector="button.maybe-exists", raise_on_failure=False)

    if result.success:
        print("Button clicked successfully")
        session.execute(type="click", selector="button.next")
    else:
        print(f"Click failed: {result.message}")
        # Try alternative approach
        session.execute(type="click", selector="button.alternative")
