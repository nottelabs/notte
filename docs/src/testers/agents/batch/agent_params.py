# @sniptest filename=agent_params.py
# @sniptest show=8-16
from notte_sdk import NotteClient
from notte_sdk.endpoints.agents import BatchRemoteAgent

client = NotteClient()

with client.Session() as session:
    vault = client.Vault(vault_id="vault_123")
    persona = client.Persona(persona_id="persona_456")

    batch_agent = BatchRemoteAgent(
        session=session,
        reasoning_model="anthropic/claude-3.5-sonnet",
        max_steps=20,
        use_vision=True,
        vault=vault,
        persona=persona,
        _client=client,
    )
