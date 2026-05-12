"""Example: Using BitwardenVault with a local notte agent.

Prerequisites:
- `bws` CLI installed (https://github.com/bitwarden/sdk/releases)
- BWS_ACCESS_TOKEN environment variable set (or pass access_token directly)
- Secrets stored in Bitwarden Secrets Manager with JSON values:
  {"url": "https://github.com/login", "password": "...", "username": "...", "email": "..."}

Usage:
    export BWS_ACCESS_TOKEN="0.your-token-here..."  # pragma: allowlist secret
    export NOTTE_API_KEY="your-notte-api-key"  # pragma: allowlist secret
    python agent.py
"""

from dotenv import load_dotenv
from notte_core.credentials.bitwarden import BitwardenVault
from notte_sdk import NotteClient

_ = load_dotenv()


def main():
    notte = NotteClient()

    with BitwardenVault() as vault, notte.Session(open_viewer=True) as session:
        agent = notte.Agent(vault=vault, session=session)
        output = agent.run(task="Go to github.com and login with your provided credentials")

    print(output)
    if not output.success:
        exit(-1)


if __name__ == "__main__":
    main()
