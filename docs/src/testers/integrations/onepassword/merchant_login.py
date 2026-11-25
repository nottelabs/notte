# @sniptest filename=merchant_login.py
# @sniptest typecheck_only=true
import os
from urllib.parse import urlsplit

from notte_sdk import ExpectedFunctionError, NotteClient
from onepassword import Client
from playwright.async_api import async_playwright

# Fixed in code, not passed as a run variable, so a caller cannot send the login elsewhere.
LOGIN_URL = "https://portal.example.com/login"
LOGIN_ORIGIN = "https://portal.example.com"

client = NotteClient()


class WrongLoginSite(ExpectedFunctionError):
    """Ends the run as rejected, so self-healing never rewrites the check."""


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


async def run(username_ref: str, password_ref: str):
    vault = await Client.authenticate(
        auth=os.environ["OP_SERVICE_ACCOUNT_TOKEN"],
        integration_name="Notte Function",
        integration_version="1.0.0",
    )
    username = await vault.secrets.resolve(username_ref)
    password = await vault.secrets.resolve(password_ref)

    # No saved browser logs or replay, since the page holds the credentials.
    with client.Session(log_session=False, record_session=False) as session:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(session.cdp_url())
            page = browser.contexts[0].pages[0]
            await page.goto(LOGIN_URL)
            if origin(page.url) != LOGIN_ORIGIN:
                raise WrongLoginSite(f"Refusing to fill credentials on {origin(page.url)}")
            await page.get_by_label("Username").fill(username)
            await page.get_by_label("Password").fill(password)
            await page.get_by_role("button", name="Sign in").click()
            # Fails with a timeout if the site rejects the login.
            await page.get_by_role("button", name="Account").wait_for(timeout=15_000)
            return {"session_id": session.session_id, "url": page.url}
