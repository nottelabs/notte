from dotenv import load_dotenv
from notte_sdk import NotteClient

# Load environment variables
_ = load_dotenv()

"""
Add credentials from environment variables for a given URL.

You should set the following environment variables for a given URL, i.e github.com:

"""

notte = NotteClient()
with notte.Vault() as vault, notte.Session(headless=False) as session:
    _ = vault.add_credentials_from_env(url="https://github.com/")

    creds = vault.get_credentials("github.com")

    if creds is None:
        raise ValueError("Vault contains no creds for github, try setting your env variables")

    for cred_type in ["email", "password", "mfa_secret"]:
        if creds.get(cred_type) is None:
            raise ValueError(f"No {cred_type} found for github.com, make sure your env variables are set correctly")

    agent = notte.Agent(vault=vault, session=session)
    response = agent.run(
        task="Go to the nottelabs/notte repo and star it. If it’s already starred (meaning, the text of the button says 'Starred' instead of 'Star'), don’t unstar it.You will need to sign in (including with your MFA). Be resilient.",
    )

    if not response.success:
        exit(-1)
