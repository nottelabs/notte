import pytest
from notte_browser.session import NotteSession
from notte_core.actions import ClickAction, FillAction
from notte_core.common.config import PerceptionType

from tests.mock.mock_service import MockLLMService
from tests.mock.mock_service import patch_llm_service as _patch_llm_service

patch_llm_service = _patch_llm_service


@pytest.fixture
def mock_llm_service() -> MockLLMService:
    return MockLLMService(mock_response="")


@pytest.mark.asyncio
async def test_google_flights(patch_llm_service) -> None:
    async with NotteSession(headless=True, viewport_width=1280, viewport_height=1080) as page:
        perception_type = PerceptionType.FAST
        _ = await page.aexecute(type="goto", value="https://www.google.com/travel/flights")
        _ = await page.aobserve(perception_type=perception_type)
        cookie_node = page.snapshot.dom_node.find("B2")
        if cookie_node is not None and "reject" in cookie_node.text.lower():
            _ = await page.aexecute(type="click", action_id="B2", enter=False)  # reject cookies
            _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(type="fill", action_id="I3", value="Paris", enter=True)
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(type="fill", action_id="I4", value="London", enter=True)
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(type="fill", action_id="I5", value="14/06/2025", enter=True)
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(type="fill", action_id="I6", value="02/07/2025", enter=True)
        _ = await page.aobserve(perception_type=perception_type)
        _ = await page.aexecute(type="click", action_id="B7")
        _ = await page.aobserve(perception_type=perception_type)


async def test_google_flights_with_agent(patch_llm_service) -> None:
    with NotteSession(
        headless=True,
        viewport_width=1280,
        viewport_height=1080,
    ) as page:
        perception_type = PerceptionType.FAST
        # observe a webpage, and take a random action
        _ = await page.aexecute(type="goto", value="https://www.google.com/travel/flights")
        _ = await page.aobserve(perception_type=perception_type)
        cookie_node = page.snapshot.dom_node.find("B2")
        if cookie_node is not None:
            _ = page.execute(ClickAction(id="B2"))
        _ = page.execute(FillAction(id="I3", value="Paris", press_enter=True))
        _ = page.execute(FillAction(id="I4", value="London", press_enter=True))
        _ = page.execute(FillAction(id="I5", value="14/06/2025"))
        _ = page.execute(FillAction(id="I6", value="02/07/2025"))
        _ = page.execute(ClickAction(id="B7"))


@pytest.mark.asyncio
async def test_observe_with_instructions() -> None:
    async with NotteSession() as session:
        _ = await session.aexecute(type="goto", value="https://www.notte.cc")
        obs = await session.aobserve(instructions="Open the docs page")
        if obs.space.is_empty():
            raise ValueError(f"No actions available for space: {obs.space.description}")
        action = obs.space.first()
        _ = await session.aexecute(type=action.type, action_id=action.id)
        obs = await session.aobserve(perception_type=PerceptionType.FAST)
        assert obs.metadata.url.startswith("https://docs.notte.cc")
