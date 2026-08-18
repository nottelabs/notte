from typing import cast
from unittest.mock import AsyncMock

import pytest
from notte_browser.controller import (
    _BLOB_CAPTURE_DISPOSE,
    _BLOB_CAPTURE_HOOK,
    _evaluate_blob_expression,
    _main_world_evaluate,
    _resolve_locator_frame,
)
from notte_browser.playwright_async_api import CDPSession, Frame, Locator


@pytest.mark.asyncio
async def test_main_world_evaluate_returns_runtime_value() -> None:
    cdp = AsyncMock()
    cdp.send.return_value = {"result": {"value": "captured"}}

    value = await _main_world_evaluate(cast("CDPSession", cdp), "expression", await_promise=True)

    assert value == "captured"
    cdp.send.assert_awaited_once_with(
        "Runtime.evaluate",
        {"expression": "expression", "awaitPromise": True, "returnByValue": True},
    )


@pytest.mark.asyncio
async def test_main_world_evaluate_surfaces_javascript_errors() -> None:
    cdp = AsyncMock()
    cdp.send.return_value = {
        "result": {"type": "object"},
        "exceptionDetails": {
            "text": "Uncaught",
            "exception": {"description": "Error: blob read failed"},
        },
    }

    with pytest.raises(RuntimeError, match=r"^CDP Runtime\.evaluate failed: Error: blob read failed$"):
        _ = await _main_world_evaluate(cast("CDPSession", cdp), "expression")


@pytest.mark.asyncio
@pytest.mark.parametrize("frame_url", ["https://top.example/frame", "https://cross-origin.example/frame"])
async def test_blob_capture_uses_locator_owner_frame(frame_url: str) -> None:
    frame = AsyncMock()
    frame.url = frame_url
    handle = AsyncMock()
    handle.owner_frame.return_value = frame
    locator = AsyncMock()
    locator.element_handle.return_value = handle

    resolved_frame = await _resolve_locator_frame(cast("Locator", locator))
    value = await _evaluate_blob_expression(cast("Frame", resolved_frame), "expression")

    assert resolved_frame is frame
    assert value is frame.evaluate.return_value
    frame.evaluate.assert_awaited_once_with("expression", isolated_context=False)
    handle.dispose.assert_awaited_once_with()


def test_blob_capture_hook_can_release_retained_blobs() -> None:
    assert "clear: () => blobs.clear()" in _BLOB_CAPTURE_HOOK
    assert "URL.createObjectURL = origCreate" in _BLOB_CAPTURE_HOOK
    assert _BLOB_CAPTURE_DISPOSE == "window.__notte_blob_capture?.dispose?.()"
