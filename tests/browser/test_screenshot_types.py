import pytest
from notte_browser.session import NotteSession
from notte_core.actions import FillAction, GotoAction
from notte_core.common.config import ScreenshotType
from notte_core.utils.webp_replay import WebpReplay
from PIL import Image


@pytest.mark.asyncio
async def test_different_screenshot_types_produce_different_screenshots() -> None:
    """
    Test that when running sessions with different screenshot types (raw, full, last_action),
    we get different screenshots for each type.
    """
    screenshot_types: list[ScreenshotType] = ["raw", "full", "last_action"]
    screenshots: dict[ScreenshotType, Image.Image] = {}
    FRAME_INDEX = -2

    for screenshot_type in screenshot_types:
        # Create a new session for each screenshot type
        async with NotteSession(screenshot_type=screenshot_type) as session:
            # Navigate to Google
            _ = await session.aexecute(GotoAction(url="https://www.google.com"))

            _ = await session.aobserve(perception_type="fast")
            # Fill the search box with id=I1 (Google's search input)
            _ = await session.aexecute(FillAction(id="I1", value="test value"))

            # Get the replay and extract the last frame
            replay: WebpReplay = session.replay()

            # Get the last frame from the replay
            # The replay contains all screenshots, so we get the last one
            last_frame = replay.frame(FRAME_INDEX)
            assert last_frame is not None, f"No frames found in replay for screenshot_type={screenshot_type}"

            # Store the screenshot data
            screenshots[screenshot_type] = last_frame

    # Verify we have screenshots for all three types
    assert len(screenshots) == 3, f"Expected 3 screenshots, got {len(screenshots)}"
    assert all(screenshot_type in screenshots for screenshot_type in screenshot_types)

    # Verify that all screenshots are different from each other
    screenshot_values = list(screenshots.values())

    # Check that all screenshots are different
    for i, screenshot_type_1 in enumerate(screenshot_types):
        for j, screenshot_type_2 in enumerate(screenshot_types):
            if i != j:
                screenshot_1 = screenshot_values[i]
                screenshot_2 = screenshot_values[j]

                assert screenshot_1 != screenshot_2, (
                    f"Screenshots for types '{screenshot_type_1}' and '{screenshot_type_2}' are identical"
                )
