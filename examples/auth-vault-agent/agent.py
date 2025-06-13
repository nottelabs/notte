from dotenv import load_dotenv
from notte_sdk import NotteClient

_ = load_dotenv()


def main():
    # Load environment variables and create vault
    # Required environment variable:
    # - NOTTE_API_KEY: your api key for the sdk
    # - GITHUB_COM_EMAIL: your github username
    # - GITHUB_COM_PASSWORD: your github password
    notte = NotteClient()

    with notte.Vault() as vault, notte.Session(headless=False) as session:
        vault.add_credentials_from_env("github.com")
        agent = notte.Agent(vault=vault, session=session)
        output = agent.run(task="Go to github.com, and login with your provided credentials")

        print(output)

    if not output.success:
        exit(-1)


if __name__ == "__main__":
    main()
