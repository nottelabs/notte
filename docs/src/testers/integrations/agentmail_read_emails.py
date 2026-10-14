# @sniptest filename=agentmail_read_emails.py
# @sniptest typecheck_only=true
import datetime as dt
import re

from notte_sdk import NotteClient

client = NotteClient()
persona = client.Persona("<your-persona-id>")

# unread emails received in the last 10 minutes
emails = persona.emails(only_unread=True, limit=10, timedelta=dt.timedelta(minutes=10))

for email in emails:
    print(f"{email.created_at} {email.sender_email}: {email.subject}")
    # pull a 6-digit verification code out of the body, if there is one
    match = re.search(r"\b\d{6}\b", email.text_content or "")
    if match:
        print(f"Verification code: {match.group()}")
    # verification links found in the body
    print(email.links())
