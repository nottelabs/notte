import pytest
from notte_browser.session import NotteSession, NotteSessionConfig
from notte_core.controller.actions import ClickAction, FillAction, GotoAction

from tests.mock.mock_service import MockLLMService


def config() -> NotteSessionConfig:
    return NotteSessionConfig().headless().set_viewport(width=1280, height=1080)


@pytest.mark.asyncio
async def test_google_flights() -> None:
    async with NotteSession(config(), llmserve=MockLLMService(mock_response="")) as page:
        _ = await page.goto("https://www.google.com/travel/flights")

        cookie_node = page.snapshot.dom_node.find("B2")
        if cookie_node is not None and "reject" in cookie_node.text.lower():
            _ = await page.execute("B2", enter=False)  # reject cookies

        _ = await page.execute("I3", "Paris", enter=True)
        _ = await page.execute("I4", "London", enter=True)
        _ = await page.execute("I5", "14/06/2025", enter=True)
        _ = await page.execute("I6", "02/07/2025", enter=True)
        _ = await page.execute("B7", None)


@pytest.mark.asyncio
async def test_google_flights_with_agent() -> None:
    cfg = config().disable_perception()

    async with NotteSession(config=cfg, llmserve=MockLLMService(mock_response="")) as page:
        # observe a webpage, and take a random action
        _ = await page.act(GotoAction(url="https://www.google.com/travel/flights"))
        cookie_node = page.snapshot.dom_node.find("B2")

        if cookie_node is not None:
            _ = await page.act(ClickAction(id="B2"))

        _ = await page.act(FillAction(id="I3", value="Paris", press_enter=True))
        _ = await page.act(FillAction(id="I4", value="London", press_enter=True))
        _ = await page.act(FillAction(id="I5", value="14/06/2025"))
        _ = await page.act(FillAction(id="I6", value="02/07/2025"))
        _ = await page.act(ClickAction(id="B7"))
