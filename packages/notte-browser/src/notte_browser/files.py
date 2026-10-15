# BrowserWindow is imported only for annotations; snapshot imports is_raw_file locally.
# pyright: reportImportCycles=false

from __future__ import annotations

import base64
import json
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from notte_core.actions import DownloadFileAction, UploadFileAction
from notte_core.logging import logger
from notte_core.raw_file import DEFAULT_RAW_FILE_SELECTORS, get_file_ext, get_filename
from notte_core.snapshot import BrowserSnapshot
from notte_core.storage import BaseStorage

from notte_browser.dom.locate import locate_element, locate_file_upload_element, selectors_through_shadow_dom
from notte_browser.driver import CDPSession, Frame, Locator, evaluate_in_main_world
from notte_browser.errors import (
    FailedToDownloadFileError,
    FailedToGetFileError,
    FailedToUploadFileError,
    NoStorageObjectProvidedError,
)
from notte_browser.js import script

if TYPE_CHECKING:
    from notte_browser.window import BrowserWindow


def is_raw_file(window: BrowserWindow) -> bool:
    if window.goto_response is None:
        return get_file_ext(headers=None, url=window.page.url) is not None

    if window.goto_response.url != window.page.url:
        window.goto_response = None
        return is_raw_file(window)

    return (
        "content-type" in window.goto_response.headers
        and "text/html" not in window.goto_response.headers["content-type"]
    )


async def download_raw_file(window: BrowserWindow) -> tuple[bytes, str]:
    if not is_raw_file(window):
        raise ValueError("Page is not a file")
    resp = await window.page.request.get(window.page.url)

    headers = resp.headers
    filename = get_filename(headers, window.page.url)
    return await resp.body(), filename


# Page-side implementation: js/blob_capture_hook.js
_BLOB_CAPTURE_HOOK = script("blob_capture_hook.js")

_BLOB_CAPTURE_DISPOSE = "window.__notte_blob_capture?.dispose?.()"

# Page-side implementation: js/blob_read.js
_BLOB_READ_SCRIPT = script("blob_read.js")


async def _main_world_evaluate(cdp: CDPSession, expression: str, await_promise: bool = False) -> Any:
    """Evaluate an expression in the page's main world and return its value."""
    raw_response = cast(
        "object",
        await cdp.send(  # pyright: ignore [reportUnknownMemberType]
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": await_promise, "returnByValue": True},
        ),
    )
    response = cast("dict[str, Any]", raw_response) if isinstance(raw_response, dict) else {}
    raw_exception_details: Any = response.get("exceptionDetails")
    if isinstance(raw_exception_details, dict):
        exception_details = cast("dict[str, Any]", raw_exception_details)
        raw_exception: Any = exception_details.get("exception")
        exception = cast("dict[str, Any]", raw_exception) if isinstance(raw_exception, dict) else None
        description = exception.get("description") if exception is not None else None
        message = description if isinstance(description, str) else exception_details.get("text", "unknown error")
        raise RuntimeError(f"CDP Runtime.evaluate failed: {message}")
    result: Any = response.get("result")
    if not isinstance(result, dict):
        return None
    return cast("dict[str, Any]", result).get("value")


async def _resolve_locator_frame(locator: Locator) -> Frame:
    """Return the frame containing a locator without retaining its element handle."""
    handle = await locator.element_handle()
    try:
        frame = await handle.owner_frame()
    finally:
        await handle.dispose()
    if frame is None:
        raise FailedToDownloadFileError()
    return frame


def _should_persist_download(*, manually_fetched: bool, captures_browser_downloads: bool) -> bool:
    """Return whether the file helper owns persistence for a downloaded file."""
    return manually_fetched or not captures_browser_downloads


async def _evaluate_blob_expression(
    frame: Frame,
    expression: str,
    *,
    cdp: CDPSession | None = None,
    await_promise: bool = False,
) -> Any:
    """Evaluate Blob capture code in the frame that owns the clicked locator."""
    if cdp is not None:
        return await _main_world_evaluate(cdp, expression, await_promise=await_promise)
    return await evaluate_in_main_world(frame, expression)


async def upload_file(
    window: BrowserWindow,
    locator: Locator,
    action: UploadFileAction,
    remaining_ms: Callable[[], float],
    prev_snapshot: BrowserSnapshot | None,
    *,
    storage: BaseStorage | None,
    verbose: bool = False,
) -> bool:
    """Upload a file; return whether the bounding-box fallback completed the action."""
    file_path = action.file_path
    if storage is None or storage.upload_dir is None:
        raise NoStorageObjectProvidedError(action.name())

    file_chooser_flag = False
    upload_file_path = await storage.get_file(file_path)

    if upload_file_path is None:
        raise FailedToGetFileError(action.id, file_path)

    if prev_snapshot is not None:
        locator_node = prev_snapshot.dom_node.find(action.id)

        if locator_node is not None and locator_node.attributes is not None:
            clickable_els = ["button", "a"]

            # To Do:
            # try except for file chooser with set input files fallback
            # drag and drop handler
            # use validation within action to improve handling?
            # change action to take list of file paths for simul multiple file upload?

            if locator_node.attributes.tag_name in clickable_els:
                if verbose:
                    logger.info("Attempting file chooser detection")
                async with window.page.expect_file_chooser(timeout=remaining_ms()) as fc:
                    await locator.click(timeout=remaining_ms())
                file_chooser = await fc.value
                await file_chooser.set_files(upload_file_path)
                file_chooser_flag = True
            else:
                new_locator_node = None

                try:
                    new_locator_node = locate_file_upload_element(locator_node)
                except Exception as e:
                    logger.info(f"Unknown error in locate_file_upload_element: {e}")

                if verbose:
                    logger.info("Tried to locate file upload input")

                if new_locator_node is not None and new_locator_node.id != locator_node.id:
                    if verbose and new_locator_node.attributes is not None:
                        logger.info(
                            f"Found input element! {new_locator_node.attributes.tag_name}, {new_locator_node.attributes.id_name if new_locator_node.attributes.id_name is not None else None}, {new_locator_node.type}"
                        )
                    selectors = new_locator_node.computed_attributes.selectors

                    if selectors is not None:
                        if selectors.in_shadow_root:
                            if verbose:
                                logger.info(
                                    f"🔍 Resolving shadow root selectors for {new_locator_node.id} ({new_locator_node.text})"
                                )
                            selectors = selectors_through_shadow_dom(new_locator_node)

                        locator = await locate_element(window.page, selectors)

    if not file_chooser_flag:
        try:
            if verbose:
                logger.info("Trying to set files")
            await locator.set_input_files(files=[upload_file_path], timeout=remaining_ms())
        except Exception as e:
            if "Node is not an HTMLInputElement" in str(e):
                # this is a special case where the element cannot be clicked on
                # try to go to the root element throught the element bounding boxes and click on it
                bbox = await locator.bounding_box(timeout=remaining_ms())
                if bbox is None:
                    raise FailedToUploadFileError(
                        action_id=action.id,
                        file_path=file_path,
                        error=e,
                    )
                # click on the center of the element
                try:
                    async with window.page.expect_file_chooser(timeout=remaining_ms()) as fc_info:
                        await window.page.mouse.click(
                            bbox["x"] + bbox["width"] * 0.54, bbox["y"] + bbox["height"] * 0.35
                        )
                        fc = await fc_info.value
                        await fc.set_files(upload_file_path, timeout=remaining_ms())
                        return True
                except Exception:
                    logger.warning("Error setting files through bounding box...")
            else:
                logger.warning(f"Error setting files: {traceback.format_exc()}")
            raise FailedToUploadFileError(
                action_id=action.id,
                file_path=file_path,
                error=e,
            )
    return False


async def download_file(
    window: BrowserWindow,
    locator: Locator,
    action: DownloadFileAction,
    remaining_ms: Callable[[], float],
    *,
    storage: BaseStorage | None,
) -> None:
    assert action.selectors is not None
    if storage is None or storage.download_dir is None:
        raise NoStorageObjectProvidedError(action.name())

    manually_fetched = is_raw_file(window)
    if manually_fetched:
        file_content, filename = await download_raw_file(window)
        logger.info(f"Saving raw file with this filename: {filename}")
        file_path = Path(storage.download_dir) / filename
        with open(file_path, "wb") as f:
            _ = f.write(file_content)

    elif action.selectors.playwright_selector in DEFAULT_RAW_FILE_SELECTORS:
        raise ValueError(
            f"Action: '{action.name()}' with selector='{action.selectors.playwright_selector}' can only be performed on RAW files urls but url='{window.page.url}'"
        )
    else:
        # Install the blob-capture hook before the click so any
        # URL.createObjectURL call inside the click handler has
        # its Blob retained in our side map.
        blob_frame = await _resolve_locator_frame(locator)
        is_main_frame = blob_frame == window.page.main_frame
        cdp = (
            await window.page.context.new_cdp_session(window.page)
            if window.is_chromium_based and is_main_frame
            else None
        )
        try:
            # CDP's default Runtime.evaluate context is the main
            # frame. For iframe locators (including cross-origin
            # frames), Frame.evaluate targets the owning frame's
            # main world directly. Firefox also uses this path.
            _ = await _evaluate_blob_expression(blob_frame, _BLOB_CAPTURE_HOOK, cdp=cdp)

            async with window.page.expect_download(timeout=remaining_ms()) as dw:
                await locator.click(timeout=remaining_ms())
            download = await dw.value

            dl_url = download.url
            if dl_url.startswith("blob:"):
                expression = f"({_BLOB_READ_SCRIPT})({json.dumps(dl_url)})"
                value = await _evaluate_blob_expression(
                    blob_frame,
                    expression,
                    cdp=cdp,
                    await_promise=True,
                )
                b64 = value if isinstance(value, str) else None
                if b64 is None:
                    raise FailedToDownloadFileError()
                file_bytes = base64.b64decode(b64)
            else:
                # page.request shares cookies/auth with the page, so
                # same-origin protected downloads work.
                resp = await window.page.request.get(dl_url)
                if resp.status >= 400:
                    raise FailedToDownloadFileError()
                file_bytes = await resp.body()
        finally:
            try:
                _ = await _evaluate_blob_expression(blob_frame, _BLOB_CAPTURE_DISPOSE, cdp=cdp)
            except Exception as e:
                logger.warning(f"Failed to dispose the Blob capture hook: {e}")
            finally:
                if cdp is not None:
                    await cdp.detach()

        if not file_bytes:
            raise FailedToDownloadFileError()

        # Sanitize: Playwright does not strip path separators from
        # Content-Disposition-derived filenames, so a malicious
        # header can escape download_dir. Take basename only.
        safe_name = Path(download.suggested_filename).name
        if not safe_name:
            raise FailedToDownloadFileError()
        file_path = Path(storage.download_dir) / safe_name
        with open(file_path, "wb") as f:
            _ = f.write(file_bytes)

    # Raw URLs are fetched and written by the file helper itself; no
    # browser download event is emitted for an out-of-band collector
    # to capture. Native click downloads do emit such an event, so a
    # collector-backed storage must remain the sole ingester there to
    # avoid creating duplicate catalog entries.
    if _should_persist_download(
        manually_fetched=manually_fetched,
        captures_browser_downloads=storage.captures_browser_downloads,
    ):
        res = await storage.set_file(str(file_path))
        if not res:
            raise FailedToDownloadFileError()
