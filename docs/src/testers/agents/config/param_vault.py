# @sniptest filename=param_vault.py
# @sniptest show=5-10
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    vault = client.Vault(vault_id="vault_123")

    agent = client.Agent(
        session=session,
        vault=vault,  # Agent can access vault credentials
    )
