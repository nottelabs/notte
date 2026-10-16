import base64
import io

import pytest
from notte_browser.session import NotteSession
from notte_core.actions import GotoAction
from notte_core.highlighter import BoundingBox, highlight_screenshot
from notte_core.observation import Observation, Screenshot
from PIL import Image

from tests.mock.mock_browser import MockBrowserDriver


def _jpeg(width: int = 400, height: int = 300) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color="white").save(buffer, format="JPEG")
    return buffer.getvalue()


def _bbox(notte_id: str, x: float) -> BoundingBox:
    return BoundingBox(
        x=x,
        y=50,
        width=80,
        height=30,
        scroll_x=0,
        scroll_y=0,
        viewport_width=400,
        viewport_height=300,
        notte_id=notte_id,
    )


@pytest.mark.asyncio
async def test_execute_does_not_append_a_screenshot() -> None:
    async with NotteSession(window=MockBrowserDriver()) as session:
        _ = await session.aexecute(GotoAction(url="https://www.example.com"))
        _ = await session.aexecute(GotoAction(url="https://www.example.com"))

        assert len(list(session.trajectory.execution_results())) == 2
        assert list(session.trajectory.screenshots()) == []
        assert session.trajectory.last_screenshot is None


@pytest.mark.asyncio
async def test_explicit_screenshot_is_appended_to_the_trajectory() -> None:
    async with NotteSession(window=MockBrowserDriver()) as session:
        _ = await session.aexecute(GotoAction(url="https://www.example.com"))
        screenshot = await session.ascreenshot()

        assert list(session.trajectory.screenshots()) == [screenshot]
        assert session.trajectory.last_screenshot is screenshot
        assert screenshot.bytes() == screenshot.raw


def test_bytes_is_raw_and_highlighted_draws_the_bboxes() -> None:
    raw = _jpeg()
    screenshot = Screenshot(raw=raw, bboxes=[_bbox("B1", 20), _bbox("I1", 200)])

    assert screenshot.bytes() == raw
    highlighted = screenshot.highlighted()
    assert highlighted != raw
    assert Image.open(io.BytesIO(highlighted)).size == (400, 300)

    only_b1 = screenshot.highlighted(action_ids=["B1"])
    assert only_b1 not in (raw, highlighted)
    assert only_b1 == highlight_screenshot(raw, [_bbox("B1", 20)])


def test_highlighted_returns_raw_when_nothing_to_highlight() -> None:
    raw = _jpeg()
    assert Screenshot(raw=raw).highlighted() == raw
    assert Screenshot(raw=raw, bboxes=[_bbox("B1", 20)]).highlighted(action_ids=["L9"]) == raw
    assert highlight_screenshot(raw, [_bbox("B1", 20).model_copy(update={"notte_id": None})]) == raw


def test_parses_notte_1x_payload_with_last_action_id() -> None:
    """notte 1.x servers still send `last_action_id` on screenshots: it is ignored."""
    raw = _jpeg()
    screenshot_payload = {
        "raw": base64.b64encode(raw).decode(),
        "bboxes": [_bbox("B1", 20).model_dump()],
        "last_action_id": "B1",
    }

    screenshot = Screenshot.model_validate(screenshot_payload)
    assert screenshot.raw == raw
    assert [bbox.notte_id for bbox in screenshot.bboxes] == ["B1"]
    assert "last_action_id" not in screenshot.model_dump()

    observation_payload = Observation.empty().model_dump(mode="json")
    observation_payload["screenshot"] = screenshot_payload
    observation = Observation.model_validate(observation_payload)
    assert observation.screenshot.raw == raw
    assert observation.screenshot.bboxes == screenshot.bboxes
