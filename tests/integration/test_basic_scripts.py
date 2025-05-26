import pytest
from notte_browser.session import NotteSession, NotteSessionConfig
from notte_core.actions import ClickAction, FillAction, GotoAction

from tests.mock.mock_service import MockLLMService


def config() -> NotteSessionConfig:
    return NotteSessionConfig().headless().set_viewport(width=1280, height=1080)


@pytest.mark.asyncio
async def test_google_flights() -> None:
    async with NotteSession(config(), llmserve=MockLLMService(mock_response="")) as page:
        _ = await page.agoto("https://www.google.com/travel/flights")
        cookie_node = page.snapshot.dom_node.find("B2")
        if cookie_node is not None and "reject" in cookie_node.text.lower():
            _ = await page.aexecute(action_id="B2", enter=False)  # reject cookies
        _ = await page.aexecute(action_id="I3", value="Paris", enter=True)
        _ = await page.aexecute(action_id="I4", value="London", enter=True)
        _ = await page.aexecute(action_id="I5", value="14/06/2025", enter=True)
        _ = await page.aexecute(action_id="I6", value="02/07/2025", enter=True)
        _ = await page.aexecute(action_id="B7")


async def test_google_flights_with_agent() -> None:
    cfg = config().disable_perception()

    with NotteSession(config=cfg, llmserve=MockLLMService(mock_response="")) as page:
        # observe a webpage, and take a random action
        _ = page.step(GotoAction(url="https://www.google.com/travel/flights"))
        cookie_node = page.snapshot.dom_node.find("B2")
        if cookie_node is not None:
            _ = page.step(ClickAction(id="B2"))
        _ = page.step(FillAction(id="I3", value="Paris", press_enter=True))
        _ = page.step(FillAction(id="I4", value="London", press_enter=True))
        _ = page.step(FillAction(id="I5", value="14/06/2025"))
        _ = page.step(FillAction(id="I6", value="02/07/2025"))
        _ = page.step(ClickAction(id="B7"))


@pytest.mark.asyncio
async def test_observe_with_instructions() -> None:
    async with NotteSession() as session:
        obs = await session.aobserve(url="https://www.notte.cc", instructions="Open the carreer page")
        if obs.space.is_empty():
            raise ValueError(f"No actions available for space: {obs.space.description}")
        action = obs.space.first()
        obs = await session.execute(action_id=action.id)
        assert obs.metadata.url == "https://www.notte.cc/careers"
        # agent = notte.Agent(headless=False)
        # out = await agent.arun("Go to x.com and describe what you see")
