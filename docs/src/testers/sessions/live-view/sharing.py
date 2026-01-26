# @sniptest filename=sharing.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Get viewer URL
    debug_info = session.debug_info()
    print(f"Share this URL with your team: {debug_info.debug_url}")

    # Team can watch live while you continue
    session.execute(type="click", selector="button.submit")
