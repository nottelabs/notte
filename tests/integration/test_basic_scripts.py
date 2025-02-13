import pytest

from notte.controller.actions import ClickAction, FillAction, GotoAction
from notte.env import NotteEnv, NotteEnvConfig
from notte.pipe.action.pipe import ActionSpaceType, MainActionSpaceConfig
from notte.pipe.preprocessing.pipe import PreprocessingType
from notte.pipe.scraping.pipe import ScrapingConfig, ScrapingType
from tests.mock.mock_service import MockLLMService


@pytest.mark.asyncio
async def test_google_flights() -> None:
    async with NotteEnv(headless=True, llmserve=MockLLMService(mock_response="")) as env:
        _ = await env.goto("https://www.google.com/travel/flights")
        cookie_node = env.context.node.find("B2")
        if cookie_node is not None and "reject" in cookie_node.text.lower():
            _ = await env.execute("B2", enter=False)  # reject cookies
        _ = await env.execute("I3", "Paris")
        _ = await env.execute("I4", "London")
        _ = await env.execute("I5", "14/06/2025", enter=True)
        _ = await env.execute("I6", "02/07/2025", enter=True)
        _ = await env.execute("B7", None)


async def test_google_flights_with_agent() -> None:
    config = NotteEnvConfig(
        max_steps=100,
        auto_scrape=False,
        processing_type=PreprocessingType.DOM,
        scraping=ScrapingConfig(type=ScrapingType.SIMPLE),
        action=MainActionSpaceConfig(type=ActionSpaceType.SIMPLE),
    )

    env = NotteEnv(headless=False, config=config, llmserve=MockLLMService(mock_response=""))
    await env.start()
    # observe a webpage, and take a random action
    _ = await env.raw_step(GotoAction(url="https://www.google.com/travel/flights"))
    cookie_node = env.context.node.find("B2")
    if cookie_node is not None:
        _ = await env.raw_step(ClickAction(id="B2"))
    _ = await env.raw_step(FillAction(id="I3", value="Paris", press_enter=True))
    _ = await env.raw_step(FillAction(id="I4", value="London", press_enter=True))
    _ = await env.raw_step(FillAction(id="I5", value="14/06/2025"))
    _ = await env.raw_step(FillAction(id="I6", value="02/07/2025"))
    _ = await env.raw_step(ClickAction(id="B7"))
