# @sniptest filename=agent_with_vault.py
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
# Run an agent with secure credential access
with client.Session() as session:
    agent = client.Agent(vault=vault, session=session, max_steps=10)
    response = agent.run(task="Go to the nottelabs/notte repo and star it. If it's already starred don't unstar it.")
