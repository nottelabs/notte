from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from notte_browser.dom.csspaths import build_csspath
from notte_browser.form_filling import FormFiller
from notte_browser.playwright_async_api import Error as PlaywrightError
from notte_core.browser.observation import Screenshot


def test_build_csspath_logs_traceback_before_using_fallback() -> None:
    with patch("notte_browser.dom.csspaths.logger") as logger:
        result = build_csspath(
            tag_name="button",
            xpath="//button",
            attributes={"title": None},  # type: ignore[dict-item]
            highlight_index=3,
        )

    assert result == "button[highlight_index='3']"
    logger.opt.assert_called_once_with(exception=True)
    logger.opt.return_value.debug.assert_called_once_with("Failed to build CSS path; using the fallback selector")


@pytest.mark.asyncio
async def test_select_field_uses_quiet_log_for_expected_exact_match_failure() -> None:
    exact_match_error = PlaywrightError("No exact match")
    field = MagicMock()
    field.select_option = AsyncMock(side_effect=[exact_match_error, None])
    field.evaluate = AsyncMock(return_value=[{"value": "CH", "text": "Switzerland"}])
    filler = FormFiller(page=MagicMock())

    with (
        patch("notte_browser.form_filling.logger") as logger,
        patch("notte_browser.form_filling.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await filler._fill_select_field(
            field=field,
            field_type="country",
            value="switzerland",
        )

    assert result is True
    assert field.select_option.await_count == 2
    logger.opt.assert_not_called()
    logger.debug.assert_any_call(
        "Exact match failed for {} field; trying case-insensitive option matching: {}",
        "country",
        exact_match_error,
    )


def test_invalid_screenshot_logs_traceback_before_using_empty_screenshot() -> None:
    with patch("notte_core.browser.observation.logger") as logger:
        screenshot = Screenshot(raw=b"not an image")

    assert screenshot.raw
    logger.opt.assert_called_once_with(exception=True)
    logger.opt.return_value.debug.assert_called_once_with("Failed to decode screenshot data; using an empty screenshot")


def test_unexpected_screenshot_error_is_not_swallowed() -> None:
    with patch("notte_core.browser.observation.Image.open", side_effect=RuntimeError("unexpected")):
        with pytest.raises(RuntimeError, match="unexpected"):
            Screenshot(raw=b"not an image")
