# @sniptest filename=param_vault.py
vault = client.Vault(vault_id="vault_123")

agent = client.Agent(
    session=session,
    vault=vault,  # Agent can access vault credentials
)
