# @sniptest filename=sms_read.py
from collections.abc import Sequence

from notte_sdk import NotteClient
from notte_sdk.types import SMSResponse

client = NotteClient()


def extract_code(messages: Sequence[SMSResponse]) -> str:
    # Extract verification code from messages
    for msg in messages:
        if msg.body and "code" in msg.body.lower():
            return msg.body
    return ""


# Create persona with phone number
persona = client.Persona(create_phone_number=True)
phone_number = persona.info.phone_number

# Use in session
with client.Session() as session:
    # Trigger SMS (e.g., 2FA code)
    if phone_number:
        session.execute(type="fill", selector="input[name='phone']", value=phone_number)
        session.execute(type="click", selector="button.send-code")

        # Read SMS from persona
        messages = persona.sms()

        # Extract verification code
        code = extract_code(messages)
