from dotenv import load_dotenv
from notte_agent import Agent
from notte_sdk import NotteClient

_ = load_dotenv()


def main():
    # Load environment variables and create vault
    # Required environment variable:
    # - VAULT_ID: the id of your vault
    # - NOTTE_API_KEY: your api key for the sdk
    # - GITHUB_COM_EMAIL: your github username
    # - GITHUB_COM_PASSWORD: your github password
    client = NotteClient()

    with client.vaults.create() as vault:
        vault.add_credentials_from_env("github.com")
        agent = Agent(vault=vault)
        output = agent.run(
            ("Go to github.com, and login with your provided credentials"),
        )
        print(output)


if __name__ == "__main__":
    main()
