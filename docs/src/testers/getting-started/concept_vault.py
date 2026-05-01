# @sniptest filename=concept_vault.py
# @sniptest show=5-9
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    vault = client.Vault()
    vault.add_credentials(url="https://github.com", email="...", password="...")
    agent = client.Agent(session=session, vault=vault)
    agent.run(task="Login to GitHub")
