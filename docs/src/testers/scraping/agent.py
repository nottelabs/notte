# @sniptest filename=authenticated_scrape.py
from notte_core.credentials import EMAIL, PASSWORD
from notte_sdk import NotteClient
from pydantic import BaseModel


class LinkedInConversation(BaseModel):
    recipient: str
    messages: list[str]


client = NotteClient()
vault = client.Vault(vault_id="<your-vault-id>")

with client.Session(vault_id=vault.vault_id) as session:
    # Log in: the vault replaces the EMAIL / PASSWORD placeholders with your real credentials
    session.execute(type="goto", url="https://www.linkedin.com/login")
    session.execute(type="form_fill", value={"email": EMAIL, "current_password": PASSWORD})
    session.execute(type="click", selector="button[type='submit']")

    # Navigate to your messages and extract the most recent conversation
    session.execute(type="goto", url="https://www.linkedin.com/messaging/")
    conversation = session.scrape(
        instructions="Extract the last 10 messages from my most recent conversation",
        response_format=LinkedInConversation,
    )
print(conversation)
