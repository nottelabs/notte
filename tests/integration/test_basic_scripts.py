import pytest

from notte.env import NotteEnv
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
