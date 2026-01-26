# @sniptest filename=vaults_manual.py
from notte_sdk import NotteClient

client = NotteClient()

# Creating a new vault
vault = client.Vault()

# Add your credentials securely
vault.add_credentials(
    url="https://github.com/",
    email="<your-email>",
    password="<your-password>",
)

# remove a credential from the vault
vault.delete_credentials(url="https://github.com/")

# list all credentials in the vault
credentials = vault.list_credentials()
print(credentials)

# delete the vault when you don't need it anymore
vault.delete()

# you can also list your active vaults as follows:
active_vaults = client.vaults.list()
print(active_vaults)
