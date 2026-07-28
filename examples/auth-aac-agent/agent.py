"""Example: Using AacVault with a local notte agent.

Prerequisites:
- `aac` CLI installed (https://github.com/bitwarden/agent-access/releases)
- User running `aac listen` on their machine (connected to their Bitwarden vault)
- Pairing token from `aac listen` output

Usage:
    # Terminal 1: User starts aac listen
    aac listen

    # Terminal 2: Run this agent with the pairing token
    export NOTTE_API_KEY="your-notte-api-key"  # pragma: allowlist secret
    python agent.py --token ABC-DEF-GHI
"""

import argparse
import os

from dotenv import load_dotenv
from notte_core.credentials.aac import AacVault
from notte_sdk import NotteClient

_ = load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Run notte agent with aac vault")
    parser.add_argument("--token", help="aac pairing token (or set AAC_TOKEN env var)")
    args = parser.parse_args()

    token = args.token or os.environ.get("AAC_TOKEN")
    if not token:
        print("Error: provide --token or set AAC_TOKEN env var")
        print("Run 'aac listen' in another terminal to get a pairing token")
        exit(1)

    notte = NotteClient()

    with AacVault(token=token) as vault, notte.Session(open_viewer=True) as session:
        agent = notte.Agent(vault=vault, session=session)
        output = agent.run(task="Go to github.com and login with your provided credentials")

    print(output)
    if not output.success:
        exit(-1)


if __name__ == "__main__":
    main()
