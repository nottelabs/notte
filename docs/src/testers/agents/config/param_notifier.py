# @sniptest filename=param_notifier.py
# @sniptest show=4-9
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # Agent with notification via email
    agent = client.Agent(
        session=session,
        # Notifications can be configured in the Notte console
    )
