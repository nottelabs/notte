# @sniptest filename=okta_mfa_agent.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient

client = NotteClient()

vault = client.Vault(vault_id="<your-vault-id>")

with client.Session(profile={"id": "<your-profile-id>", "persist": True}) as session:
    agent = client.Agent(session=session, vault=vault, max_steps=20, use_vision=True)
    response = agent.run(
        task=(
            "Sign in to Okta. If offered a choice of security method, choose "
            "Google Authenticator and enter the generated code."
        ),
        url="https://<your-org>.okta.com",
    )

print(response.success)
print(response.answer)
