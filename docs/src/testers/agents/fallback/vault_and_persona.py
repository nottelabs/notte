from notte_sdk import NotteClient

client = NotteClient()

vault = client.Vault(vault_id="vault_123")
persona = client.Persona("persona_123")

with client.Session() as session:
    with client.AgentFallback(
        session,
        task="Login and navigate to settings",
        vault_id=vault.vault_id,
        persona_id=persona.persona_id,
    ) as fb:
        # Try logging in with deterministic actions
        session.execute(type="fill", selector="#email", value="user@example.com")
        session.execute(type="fill", selector="#password", value="password123")
        session.execute(type="click", selector="#login")

        # If login flow changed, the agent uses the vault credentials
        # and the persona's email/phone for verification steps
