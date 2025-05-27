import asyncio
import os

from dotenv import load_dotenv
from notte_sdk.client import NotteClient

from notte import Agent, Session

_ = load_dotenv()

client = NotteClient(api_key=os.environ["NOTTE_API_KEY"])


def load_env_vars(var_dict: dict[str, str]) -> dict[str, str]:
    creds_dict: dict[str, str] = {}
    for cred_key, env_var in var_dict.items():
        var = os.getenv(env_var)
        if var is None:
            raise ValueError(f"Set the {env_var} env variable for the example to work")
        creds_dict[cred_key] = var

    return creds_dict


PROMPT = """Task: Go to ubereats, and order me a burger menu.

- Go to https://www.ubereats.com, and login with your provided credentials.
  - Make sure you login using your authenticator app / mfa. By default, it tells you to use a code from your email, don't do that.
  - After you've put in the code, that means you've logged in.
- Add a burger menu to your cart.
  - Click the parts of the menu you want
  - Scroll down until you see the button "Add to order".
  - Click the add to order button
- Go all the way through filling your credit card credentials, but don't click to commit (end at that point).
"""


async def main():
    cred_env_vars = dict(email="UBER_EMAIL", password="UBER_PASSWORD", mfa_secret="UBER_MFA_SECRET")
    cc_env_vars = dict(
        card_holder_name="CREDIT_CARD_HOLDER",
        card_number="CREDIT_CARD_NUMBER",
        card_cvv="CREDIT_CARD_CVV",
        card_full_expiration="CREDIT_CARD_EXPIRATION",
    )

    async with Session(headless=False) as session:
        with client.vaults.create() as vault:
            vault.add_credentials(url="uber.com", **load_env_vars(cred_env_vars))
            vault.set_credit_card(**load_env_vars(cc_env_vars))
            agent = Agent(vault=vault, max_steps=30, session=session)

            _ = await agent.arun(PROMPT)

            _ = input("Waiting for you to fill in your order")


if __name__ == "__main__":
    asyncio.run(main())
