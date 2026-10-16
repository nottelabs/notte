# @sniptest filename=concept_vault.py
# @sniptest show=5-10
from notte_core.credentials import EMAIL, PASSWORD
from notte_sdk import NotteClient

client = NotteClient()
with client.Vault() as vault:
    vault.add_credentials(url="https://github.com", email="...", password="...")
    with client.Session(vault_id=vault.vault_id) as session:
        session.execute(type="goto", url="https://github.com/login")
        # EMAIL / PASSWORD are placeholders: the vault fills in the real values
        session.execute(type="form_fill", value={"email": EMAIL, "current_password": PASSWORD})
