# @sniptest filename=concept_identity.py
# @sniptest show=4-6
from notte_sdk import NotteClient

client = NotteClient()
with client.Persona() as persona:  # Generate synthetic identity
    print(f"Sign up with {persona.email}")
    emails = persona.emails(only_unread=True)  # Read verification emails
