import os

from dotenv import load_dotenv
from notte_agent import Agent
from notte_sdk import NotteClient


def main():
    _ = load_dotenv()

    # Load environment variables and create vault
    # Required environment variable:
    # - VAULT_ID: the id of your vault
    # - NOTTE_API_KEY: your api key for the sdk
    # - GITHUB_COM_EMAIL: your github username
    # - GITHUB_COM_PASSWORD: your github password
    client = NotteClient()

    vault_id = os.getenv("NOTTE_VAULT_ID")
    if vault_id is None:
        raise ValueError("Set NOTTE_VAULT_ID env variable to a valid Notte vault id")

    vault = client.vaults.get(vault_id)

    URL = "github.com"
    if not vault.has_credential(URL):
        vault.add_credentials_from_env(URL)

    agent = Agent(vault=vault)

    output = agent.run(
        ("Go to github.com, and login with your provided credentials"),
    )
    print(output)


if __name__ == "__main__":
    # Run the async function
    main()
