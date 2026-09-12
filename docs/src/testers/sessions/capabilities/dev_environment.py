# @sniptest filename=dev_environment.py
# @sniptest show=1-11
import os

from notte_sdk import NotteClient

client = NotteClient()

# Only use live view in development
is_dev = os.getenv("ENV") == "development"

with client.Session(open_viewer=is_dev) as session:
    session.execute(type="goto", url="https://example.com")

status = session.status()
