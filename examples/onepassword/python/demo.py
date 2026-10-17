import asyncio
import json
import os
import sys

from notte_sdk import NotteClient
from onepassword import Client, Secrets
from playwright.async_api import Page, async_playwright


class VaultFormError(RuntimeError):
    pass


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

    def safe_error(error):
        if isinstance(error, VaultFormError):
            return error
        return VaultFormError(f"Vault form failed: {stage} [{type(error).__name__}] (session {session_id})")

    try:
        with client.Session(max_duration_minutes=3) as session:
            session_id = session.session_id
            stage = "open test form"
            try:
                async with async_playwright() as driver:
                    browser = await driver.chromium.connect_over_cdp(session.cdp_url())
                    try:
                        page = browser.contexts[0].pages[0]
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
                    finally:
                        failed = sys.exception() is not None
                        if not failed:
                            stage = "disconnect browser"
                        try:
                            await asyncio.wait_for(browser.close(), timeout=5)
                        except Exception:
                            if not failed:
                                raise RuntimeError("Browser disconnect failed") from None
            except Exception as error:
                raise safe_error(error) from None
        return {"submitted": True, "session_id": session_id}
    except Exception as error:
        raise safe_error(error) from None


if __name__ == "__main__":
    try:
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(run_demo())))
    except Exception as error:
        print(str(error))
        raise SystemExit(1) from None
