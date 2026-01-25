# @sniptest filename=param_persona.py
persona = client.Persona(persona_id="persona_456")

agent = client.Agent(
    session=session,
    persona=persona,  # Agent can use persona information
)
