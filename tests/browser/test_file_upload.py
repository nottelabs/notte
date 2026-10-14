import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import notte_browser.controller as controller_module
import pytest
from notte_browser.controller import BrowserController, _ActionBudget
from notte_browser.window import BrowserWindow
from notte_core.actions import UploadFileAction
from notte_core.storage import BaseStorage


@pytest.mark.asyncio
@pytest.mark.parametrize("bounding_box_fallback", [False, True])
async def test_upload_preserves_press_enter_sequence(
    monkeypatch: pytest.MonkeyPatch, bounding_box_fallback: bool
) -> None:
    window = MagicMock()
    window.short_wait = AsyncMock()
    window.page.keyboard.press = AsyncMock()
    window.page.mouse.click = AsyncMock()
    locator = AsyncMock()
    locator.bounding_box.return_value = {"x": 0, "y": 0, "width": 100, "height": 100}
    if bounding_box_fallback:
        locator.set_input_files.side_effect = RuntimeError("Node is not an HTMLInputElement")
    chooser = AsyncMock()
    chooser_result = asyncio.get_running_loop().create_future()
    chooser_result.set_result(chooser)
    chooser_context = MagicMock()
    chooser_context.value = chooser_result
    window.page.expect_file_chooser.return_value.__aenter__.return_value = chooser_context
    storage = MagicMock()
    storage.upload_dir = "uploads"
    storage.get_file = AsyncMock(return_value="uploads/example.txt")
    monkeypatch.setattr(controller_module, "locate_element", AsyncMock(return_value=locator))

    controller = BrowserController(verbose=False, storage=cast(BaseStorage, storage))
    await controller._interact(  # pyright: ignore[reportPrivateUsage]
        cast(BrowserWindow, window),
        UploadFileAction(selector="#upload", file_path="example.txt", press_enter=True),
        _ActionBudget(asyncio.get_running_loop().time() + 10),
        None,
    )

    locator.set_input_files.assert_awaited_once()
    if bounding_box_fallback:
        chooser.set_files.assert_awaited_once()
        window.short_wait.assert_not_awaited()
        window.page.keyboard.press.assert_not_awaited()
    else:
        window.short_wait.assert_awaited_once()
        window.page.keyboard.press.assert_awaited_once_with("Enter")
