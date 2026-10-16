import asyncio
import json
import os

from notte_sdk import NotteClient
from onepassword import Client, Secrets
from playwright.async_api import Page


async def fill_login(page: Page, username_ref: str, password_ref: str) -> None:
    """Read the two requested fields and fill the page's labeled login form."""
    vault = await Client.authenticate(
        auth=os.environ["OP_SERVICE_ACCOUNT_TOKEN"],
        integration_name="Notte browser example",
        integration_version="1.0.0",
    )
    username = await vault.secrets.resolve(username_ref)
    password = await vault.secrets.resolve(password_ref)
    await page.get_by_label("Username", exact=True).fill(username)
    await page.get_by_label("Password", exact=True).fill(password)
    if await page.get_by_label("Username", exact=True).input_value() != username:
        raise RuntimeError("Username was not filled")
    if await page.get_by_label("Password", exact=True).input_value() != password:
        raise RuntimeError("Password was not filled")
    await page.get_by_role("button", name="Sign in", exact=True).click()


async def run_demo() -> dict:
    for name in ["OP_SERVICE_ACCOUNT_TOKEN", "OP_USERNAME_REF", "OP_PASSWORD_REF"]:
        if not os.environ.get(name):
            raise RuntimeError(f"Set {name}")
    for name in ["OP_USERNAME_REF", "OP_PASSWORD_REF"]:
        Secrets.validate_secret_reference(os.environ[name])
    client = NotteClient()
    session_id = "not-created"
    stage = "create browser"
    try:
        async with client.Session(max_duration_minutes=3) as session:
            session_id = session.session_id
            stage = "open test form"
            page = await session.apage
            await page.goto("about:blank")
            await page.set_content(
                "<form onsubmit=\"event.preventDefault();document.querySelector('output').textContent='Submitted'\">"
                '<label>Username<input name="username" autocomplete="off"></label>'
                '<label>Password<input name="password" type="password" autocomplete="off"></label>'
                "<button>Sign in</button><output></output></form>"
            )
            stage = "resolve and fill login"
            await fill_login(page, os.environ["OP_USERNAME_REF"], os.environ["OP_PASSWORD_REF"])
            await page.locator("output").filter(has_text="Submitted").wait_for()
        return {"submitted": True, "session_id": session_id}
    except Exception as error:
        raise RuntimeError(f"Vault form failed: {stage} [{type(error).__name__}] (session {session_id})") from None


if __name__ == "__main__":
    try:
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(run_demo())))
    except Exception as error:
        print(str(error))
        raise SystemExit(1) from None
