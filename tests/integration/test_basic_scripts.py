import pytest

from notte.controller.actions import ClickAction, FillAction, GotoAction
from notte.env import NotteEnv, NotteEnvConfig
from tests.mock.mock_service import MockLLMService


@pytest.mark.asyncio
async def test_google_flights() -> None:
    async with NotteEnv(NotteEnvConfig().headless(), llmserve=MockLLMService(mock_response="")) as env:
        _ = await env.goto("https://www.google.com/travel/flights")
        cookie_node = env.snapshot.dom_node.find("B2")
        if cookie_node is not None and "reject" in cookie_node.text.lower():
            _ = await env.execute("B2", enter=False)  # reject cookies
        _ = await env.execute("I3", "Paris", enter=True)
        _ = await env.execute("I4", "London", enter=True)
        _ = await env.execute("I5", "14/06/2025", enter=True)
        _ = await env.execute("I6", "02/07/2025", enter=True)
        _ = await env.execute("B7", None)


@pytest.mark.asyncio
async def test_google_flights_with_agent() -> None:
    config = NotteEnvConfig().disable_perception().headless()

    env = NotteEnv(config=config, llmserve=MockLLMService(mock_response=""))
    await env.start()
    # observe a webpage, and take a random action
    _ = await env.act(GotoAction(url="https://www.google.com/travel/flights"))
    cookie_node = env.snapshot.dom_node.find("B2")
    if cookie_node is not None:
        _ = await env.act(ClickAction(id="B2"))
    _ = await env.act(FillAction(id="I3", value="Paris", press_enter=True))
    _ = await env.act(FillAction(id="I4", value="London", press_enter=True))
    _ = await env.act(FillAction(id="I5", value="14/06/2025"))
    _ = await env.act(FillAction(id="I6", value="02/07/2025"))
    _ = await env.act(ClickAction(id="B7"))
