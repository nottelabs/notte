import pytest
from notte_browser.session import NotteSession
from notte_browser.vault import VaultSecretsScreenshotMask
from notte_core.actions import FillAction
from notte_core.credentials import EMAIL

from tests.mock.mock_vault import MockVault

SECRET_EMAIL = "real-user@example.com"  # pragma: allowlist secret
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

        # Post-action screenshots (also used by `replay()`) go through the masked Playwright path.
        assert len(list(session.trajectory.all_screenshots())) >= 1


@pytest.mark.asyncio
async def test_session_without_vault_has_no_screenshot_mask() -> None:
    async with NotteSession(headless=True) as session:
        assert session.window.screenshot_mask is None
