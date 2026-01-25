# @sniptest filename=puppeteer_session_timeout.py
from notte_sdk import NotteClient

client = NotteClient()

# In Python
with client.Session(timeout_minutes=20) as session:
    # Long Puppeteer operations
    pass
