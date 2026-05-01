# @sniptest filename=context_manager.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # ... use session
    pass
# Automatically stopped here
