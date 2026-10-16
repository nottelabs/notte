# @sniptest filename=create_account.py
from notte_core.credentials import EMAIL, PASSWORD
from notte_sdk import NotteClient

client = NotteClient()
# retrieve the persona from the Notte console
# if you don't have a persona id, you can create a new persona using:
# persona = client.Persona(create_vault=True)
# print(f"Persona id: {persona.info.persona_id}")
persona = client.Persona("<your-persona-id>")

url = "https://console.notte.cc"
# create credentials for the persona (automatically generates a password and stores it in the vault)
persona.add_credentials(url=url)

# The session swaps the EMAIL / PASSWORD placeholders for the persona's real credentials
with client.Session(vault_id=persona.info.vault_id) as session:
    session.execute(type="goto", url=url)
    session.execute(type="form_fill", value={"email": EMAIL, "new_password": PASSWORD})
    session.execute(type="click", selector="button[type='submit']")

# Read the verification email sent to the persona's inbox
for email in persona.emails(only_unread=True):
    print(email.subject)
