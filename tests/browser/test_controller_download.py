from typing import cast
from unittest.mock import AsyncMock

import pytest
from notte_browser.controller import _BLOB_CAPTURE_DISPOSE, _BLOB_CAPTURE_HOOK, _main_world_evaluate
from notte_browser.playwright_async_api import CDPSession


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

    with pytest.raises(RuntimeError, match="CDP Runtime.evaluate failed: Error: blob read failed"):
        _ = await _main_world_evaluate(cast("CDPSession", cdp), "expression")


def test_blob_capture_hook_can_release_retained_blobs() -> None:
    assert "clear: () => blobs.clear()" in _BLOB_CAPTURE_HOOK
    assert "URL.createObjectURL = origCreate" in _BLOB_CAPTURE_HOOK
    assert _BLOB_CAPTURE_DISPOSE == "window.__notte_blob_capture?.dispose?.()"
