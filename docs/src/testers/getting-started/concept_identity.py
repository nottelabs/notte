# @sniptest filename=concept_identity.py
# @sniptest show=5-8
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    persona = client.Persona()  # Generate synthetic identity
    agent = client.Agent(session=session, persona=persona)
    agent.run(task="Sign up for newsletter")
