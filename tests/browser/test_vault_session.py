import pytest
from notte_browser.session import NotteSession
from notte_browser.vault import VaultSecretsScreenshotMask
from notte_core.actions import FillAction
from notte_core.credentials import EMAIL, PASSWORD
from notte_core.errors import VaultCredentialError

from tests.mock.mock_vault import MockVault

SECRET_EMAIL = "real-user@example.com"  # pragma: allowlist secret
SECRET_PASSWORD = "s3cr3t-pw"  # pragma: allowlist secret
PAGE = '<html><body><input id="email" type="email"><input id="other" type="text" value="public"></body></html>'


@pytest.mark.asyncio
async def test_vault_secret_typed_into_page_is_masked_in_screenshots() -> None:
    vault = MockVault({"about:blank": {"email": SECRET_EMAIL}})
    async with NotteSession(headless=True, vault=vault) as session:
        # The mask is installed on the window created by `astart`.
        mask = session.window.screenshot_mask
        assert isinstance(mask, VaultSecretsScreenshotMask)

        await session.window.page.set_content(PAGE)
        result = await session.aexecute(FillAction(selector="#email", value=EMAIL), raise_on_failure=True)
        assert result.success
        assert await session.window.page.locator("#email").input_value() == SECRET_EMAIL

        masked = await mask.mask(session.window.page)
        assert len(masked) == 1
        assert await masked[0].get_attribute("id") == "email"

        # Explicit screenshots go through the masked Playwright path and are recorded in the trajectory.
        screenshot = await session.ascreenshot()
        assert session.trajectory.last_screenshot is screenshot


@pytest.mark.asyncio
async def test_session_without_vault_has_no_screenshot_mask() -> None:
    async with NotteSession(headless=True) as session:
        assert session.window.screenshot_mask is None


@pytest.mark.asyncio
async def test_unvalidated_vault_credential_fails_without_typing_the_placeholder() -> None:
    vault = MockVault({"about:blank": {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}})
    async with NotteSession(headless=True, vault=vault) as session:
        await session.window.page.set_content(PAGE)
        # `#other` is a plain text input, not a password field.
        result = await session.aexecute(FillAction(selector="#other", value=PASSWORD), raise_on_failure=False)

        assert not result.success
        assert isinstance(result.exception, VaultCredentialError)
        value = await session.window.page.locator("#other").input_value()
        assert value == "public"
        assert PASSWORD not in value and SECRET_PASSWORD not in value


@pytest.mark.asyncio
async def test_plain_text_that_looks_like_a_placeholder_is_typed_as_given() -> None:
    vault = MockVault({"about:blank": {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}})
    async with NotteSession(headless=True, vault=vault) as session:
        await session.window.page.set_content(PAGE)
        other = session.window.page.locator("#other")

        # "John Doe" is the cardholder placeholder, but `#other` is no payment field.
        result = await session.aexecute(FillAction(selector="#other", value="John Doe"), raise_on_failure=True)
        assert result.success
        assert await other.input_value() == "John Doe"

        # Text merely containing placeholders is never a credential request.
        text = f"Hi John Doe, your code is 999779, reply to {EMAIL}"
        result = await session.aexecute(FillAction(selector="#other", value=text), raise_on_failure=True)
        assert result.success
        assert await other.input_value() == text

        # A value that is exactly a placeholder still resolves from the vault.
        result = await session.aexecute(FillAction(selector="#email", value=EMAIL), raise_on_failure=True)
        assert result.success
        assert await session.window.page.locator("#email").input_value() == SECRET_EMAIL
