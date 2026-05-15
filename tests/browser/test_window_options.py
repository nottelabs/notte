import pytest
from notte_browser.window import BrowserWindowOptions
from notte_sdk.types import (
    DEFAULT_HEADLESS_VIEWPORT_HEIGHT,
    DEFAULT_HEADLESS_VIEWPORT_WIDTH,
    SessionStartRequest,
)
from pydantic import ValidationError


def test_headless_window_options_preserve_16_9_aspect_ratio() -> None:
    request = SessionStartRequest(headless=True, aspect_ratio="16:9")

    options = BrowserWindowOptions.from_request(request)

    assert options.viewport_width == DEFAULT_HEADLESS_VIEWPORT_WIDTH
    assert options.viewport_height == 720


def test_headless_window_options_preserve_5_4_aspect_ratio() -> None:
    request = SessionStartRequest(headless=True, aspect_ratio="5:4")

    options = BrowserWindowOptions.from_request(request)

    assert options.viewport_width == DEFAULT_HEADLESS_VIEWPORT_WIDTH
    assert options.viewport_height == 1024
    assert options.viewport_height <= DEFAULT_HEADLESS_VIEWPORT_HEIGHT


def test_explicit_viewport_takes_precedence_over_aspect_ratio_defaulting() -> None:
    options = BrowserWindowOptions.from_request(
        SessionStartRequest(headless=True, viewport_width=1000, viewport_height=500)
    )

    assert options.viewport_width == 1000
    assert options.viewport_height == 500


def test_aspect_ratio_rejects_explicit_viewport() -> None:
    with pytest.raises(ValidationError, match="aspect_ratio cannot be set together with viewport_width"):
        SessionStartRequest(headless=True, aspect_ratio="16:9", viewport_width=1000, viewport_height=500)


def test_headless_cdp_window_options_do_not_synthesize_viewport() -> None:
    options = BrowserWindowOptions(
        headless=True,
        solve_captchas=False,
        user_agent=None,
        proxy=None,
        viewport_width=None,
        viewport_height=None,
        aspect_ratio="16:9",
        browser_type="chromium",
        chrome_args=None,
        web_security=False,
        cdp_url="ws://127.0.0.1:9222/devtools/browser/test",
        debug_port=None,
        custom_devtools_frontend=None,
    )

    assert options.viewport_width is None
    assert options.viewport_height is None
