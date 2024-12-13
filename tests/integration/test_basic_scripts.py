import pytest

from notte.env import NotteEnv
from tests.mock.mock_service import MockLLMService


@pytest.mark.asyncio
async def test_google_flights() -> None:
    async with NotteEnv(headless=True, llmserve=MockLLMService(mock_response="")) as env:
        _ = await env.goto("https://www.google.com/travel/flights")
        _ = await env.execute("B2", enter=False)  # accepts cookies
        _ = await env.execute("I3", "Paris")
        _ = await env.execute("I4", "London")
        _ = await env.execute("I5", "14/06/2025", enter=True)
        _ = await env.execute("I6", "02/07/2025", enter=True)
        _ = await env.execute("B7", None)
