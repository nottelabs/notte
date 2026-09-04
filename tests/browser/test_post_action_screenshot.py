import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from notte_browser.session import NotteSession


@pytest.mark.asyncio
async def test_post_action_screenshot_has_total_deadline() -> None:
    session = object.__new__(NotteSession)
    cancelled = asyncio.Event()

    async def stalled_screenshot() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    session.ascreenshot = AsyncMock(side_effect=stalled_screenshot)

    with patch.object(NotteSession, "POST_ACTION_SCREENSHOT_TIMEOUT_SECONDS", 0.01):
        await session._capture_post_action_screenshot()

    assert cancelled.is_set()
    session.ascreenshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_action_screenshot_failure_is_best_effort() -> None:
    session = object.__new__(NotteSession)
    session.ascreenshot = AsyncMock(side_effect=RuntimeError("renderer unavailable"))

    await session._capture_post_action_screenshot()

    session.ascreenshot.assert_awaited_once()
