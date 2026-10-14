# @sniptest filename=agentmail_signup.py
# @sniptest typecheck_only=true
from notte_sdk import NotteClient

client = NotteClient()

# a persona with an AgentMail inbox and a vault to store the generated password
persona = client.Persona(email_provider="agentmail", create_vault=True)
print(f"Persona id: {persona.info.persona_id}")
print(f"Signing up as: {persona.info.email}")

# replace with the sign-up page of the site you want an account on
url = "https://example.com/signup"

# generate a password for this site and store it in the persona's vault
persona.add_credentials(url=url)

with client.Session() as session:
    agent = client.Agent(session=session, persona=persona, max_steps=20)
    response = agent.run(
        task=(
            "Create an account with the persona's email address. "
            "If the site sends a verification code or link by email, read it from the inbox and finish verification."
        ),
        url=url,
    )
    print(response.answer)
