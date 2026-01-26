# @sniptest filename=param_session.py
# @sniptest show=5-6
from notte_sdk import NotteClient

client = NotteClient()
with client.Session(headless=False) as session:
    agent = client.Agent(session=session)
