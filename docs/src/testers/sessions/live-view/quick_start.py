# @sniptest filename=quick_start.py
from notte_sdk import NotteClient

client = NotteClient()

# Live viewer opens automatically
with client.Session(open_viewer=True) as session:
    session.execute(type="goto", url="https://example.com")
    session.execute(type="click", selector="button.submit")
    # Watch it happen in your browser!
