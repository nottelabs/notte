# @sniptest filename=param_persona.py
# @sniptest show=5-10
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    persona = client.Persona(persona_id="persona_456")

    agent = client.Agent(
        session=session,
        persona=persona,  # Agent can use persona information
    )
