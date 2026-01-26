# @sniptest filename=viewer_notebook.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Display in notebook cell
    session.viewer_notebook()
