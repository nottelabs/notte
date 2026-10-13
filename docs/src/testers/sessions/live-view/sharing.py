# @sniptest filename=sharing.py
# @sniptest show=1-13
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Get viewer URL
    viewer_url = session.status().viewer_url
    print(f"Share this URL with your team: {viewer_url}")

    # Team can watch live while you continue
    session.execute(type="click", selector="button.submit")
    assert viewer_url is not None and viewer_url.startswith("https://")
