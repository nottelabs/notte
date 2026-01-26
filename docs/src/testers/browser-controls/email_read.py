# @sniptest filename=email_read.py
from collections.abc import Sequence

from notte_sdk import NotteClient
from notte_sdk.types import EmailResponse

client = NotteClient()


def extract_link(messages: Sequence[EmailResponse]) -> str:
    # Extract verification link from messages
    for msg in messages:
        if msg.text_content and "verify" in msg.text_content.lower():
            return msg.text_content
    return ""


# Create persona with email
persona = client.Persona()

# Use in session
with client.Session() as session:
    # Trigger email (e.g., verification email)
    session.execute(type="fill", selector="input[name='email']", value=persona.info.email)
    session.execute(type="click", selector="button.send-verification")

    # Read emails from persona
    messages = persona.emails()

    # Extract verification link
    link = extract_link(messages)
