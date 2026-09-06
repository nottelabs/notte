"""`goto_and_wait` skips the post-load settle wait when the caller asked for `commit` or `domcontentloaded`."""

from types import SimpleNamespace
from typing import Any

import pytest
from notte_browser.window import BrowserWindow


class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.goto_calls: list[dict[str, Any]] = []

    def once(self, event: str, handler: Any) -> None:
        pass

    def on(self, event: str, handler: Any) -> None:
        pass

    def set_default_timeout(self, timeout: float) -> None:
        pass

    async def goto(self, url: str, **kwargs: Any) -> None:
        self.goto_calls.append({"url": url, **kwargs})
        self.url = url


def window_with(page: FakePage, monkeypatch: pytest.MonkeyPatch) -> tuple[BrowserWindow, list[str]]:
    waits: list[str] = []

    async def short_wait(self: BrowserWindow) -> None:
        waits.append("short")

    async def long_wait(self: BrowserWindow) -> None:
        waits.append("long")

    monkeypatch.setattr(BrowserWindow, "short_wait", short_wait)
    monkeypatch.setattr(BrowserWindow, "long_wait", long_wait)
    # the real property falls back to other tabs when the page is closed; only navigation is under test
    monkeypatch.setattr(BrowserWindow, "page", property(lambda self: self.resource.page))
    window = BrowserWindow.model_construct(resource=SimpleNamespace(page=page))
    return window, waits


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_until", [None, "load", "networkidle"])
async def test_full_loads_keep_the_settle_wait(monkeypatch: pytest.MonkeyPatch, wait_until: str | None) -> None:
    page = FakePage()
    window, waits = window_with(page, monkeypatch)

    await window.goto_and_wait(url="https://example.com/", wait_until=wait_until)  # type: ignore[arg-type]

    assert page.goto_calls[0]["wait_until"] == wait_until
    assert waits == ["short"]


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_until", ["commit", "domcontentloaded"])
async def test_cheap_loads_skip_the_settle_wait(monkeypatch: pytest.MonkeyPatch, wait_until: str) -> None:
    page = FakePage()
    window, waits = window_with(page, monkeypatch)

    await window.goto_and_wait(url="https://example.com/", wait_until=wait_until)  # type: ignore[arg-type]

    assert page.goto_calls[0]["wait_until"] == wait_until
    assert waits == []
