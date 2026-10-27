# @sniptest filename=session_with_vault.py
from notte_core.credentials import EMAIL, PASSWORD
from notte_sdk import NotteClient

client = NotteClient()
# Get your vault id from the Notte dashboard
vault = client.Vault(vault_id="my_vault_id")
# Add your credentials securely
vault.add_credentials(
    url="https://github.com/",
    email="my_cool_email@gmail.com",
    password="my_cool_password",
)
# Attach the vault to a session: EMAIL / PASSWORD placeholders are replaced
# by the real credentials inside the browser, never in your code
with client.Session(vault=vault) as session:
    session.execute(type="goto", url="https://github.com/login")
    session.execute(type="form_fill", value={"email": EMAIL, "current_password": PASSWORD})
