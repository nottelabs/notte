# @sniptest filename=async_persona_vault.py
import asyncio

from notte_sdk import AsyncNotteClient


async def main() -> None:
    async with AsyncNotteClient() as client:
        # `async with` creates the persona and deletes it on exit
        async with client.Persona(create_vault=True) as persona:
            print(f"Persona email: {persona.info.email}")
            await persona.add_credentials(url="https://github.com/")
            emails = await persona.emails(only_unread=True, limit=10)
            print(f"Recent emails: {emails}")

        # `await` creates the vault; delete it when you no longer need it
        vault = await client.Vault(name="async-example")
        try:
            password = vault.generate_password()  # no request, so not awaited
            await vault.add_credentials(url="https://example.com", email="me@example.com", password=password)
            print(await vault.list_credentials())
        finally:
            await vault.delete()


asyncio.run(main())
