import asyncio
from dataclasses import dataclass

import pytest
from notte_browser.session import NotteSession
from notte_sdk.types import ExecutionRequest
from patchright.async_api import Locator, expect

PASSWORD_TOGGLE = 'button[analyticsid="loginPassword"]'
EMAIL_INPUT = 'input[name="email"]'
PASSWORD_INPUT = 'input[name="password"]'
LOGIN_BUTTON = 'button[analyticsid="loginLoginBtn"]'


@pytest.fixture
def headless() -> bool:
    return True


@dataclass
class ExecutionTest:
    url: str
    steps: list[ExecutionRequest]


@pytest.fixture
def phantombuster_login() -> ExecutionTest:
    return ExecutionTest(
        url="https://phantombuster.com/login",
        steps=[
            ExecutionRequest(type="click", selector=PASSWORD_TOGGLE, value=None, enter=False),
            ExecutionRequest(type="fill", selector=EMAIL_INPUT, value="lucasgiordano@gmail.com", enter=False),
            ExecutionRequest(type="fill", selector=PASSWORD_INPUT, value="lucasgiordano", enter=False),
            ExecutionRequest(type="click", selector=LOGIN_BUTTON, value=None, enter=False),
        ],
    )


async def _test_execution(test: ExecutionTest, headless: bool) -> None:
    async with NotteSession(
        headless=headless,
    ) as page:

        async def dismiss_consent(locator: Locator) -> None:
            await locator.click()

        # The optional consent banner shifts observed action IDs and can appear
        # between actions. Dismiss it when Playwright checks actionability.
        await page.window.page.add_locator_handler(
            page.window.page.get_by_role("button", name="Deny", exact=True), dismiss_consent
        )
        _ = await page.aexecute(type="goto", url=test.url)
        _ = await page.aobserve()
        for step in test.steps:
            assert step.selector is not None
            selector = step.selector.playwright_selector
            assert selector
            target = page.window.page.locator(selector)
            await expect(target).to_have_count(1)
            result = await page.aexecute(**step.model_dump(exclude_none=True))
            assert result.success
            if selector == PASSWORD_TOGGLE:
                assert await page.window.page.locator(PASSWORD_INPUT).get_attribute("type") == "text"
            elif step.type == "fill":
                assert await target.input_value() == step.value
            _ = await page.aobserve()


@pytest.mark.live
def test_execution(phantombuster_login: ExecutionTest, headless: bool) -> None:
    asyncio.run(_test_execution(phantombuster_login, headless))
