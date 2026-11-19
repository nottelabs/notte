from unittest.mock import AsyncMock, MagicMock

import notte_browser.playwright as lifecycle
import pytest
from notte_browser.driver import Browser, Error, Playwright
from notte_browser.window import BrowserWindowOptions
from notte_sdk.types import LocalSessionStartRequest

SANDBOX_FAILED = "Browser.launch: Chromium sandboxing failed!\n================================"
SUID_HELPER_MISCONFIGURED = (
    "Browser.launch: Target page, context or browser has been closed\n"
    "[pid=1][err] [1:1:FATAL:sandbox/linux/suid/client/setuid_sandbox_host.cc:172] "
    "The SUID sandbox helper binary was found, but is not configured correctly. "
    "Rather than run without sandboxing I'm aborting now."
)


@pytest.fixture
def driver() -> MagicMock:
    playwright = MagicMock(spec=Playwright)
    playwright.chromium.launch = AsyncMock(return_value=MagicMock(spec=Browser))
    return playwright


@pytest.fixture
def linux_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lifecycle.sys, "platform", "linux")
    monkeypatch.setattr(lifecycle.os, "geteuid", lambda: 1000, raising=False)


def _options(chrome_args: list[str] | None = None) -> BrowserWindowOptions:
    return BrowserWindowOptions.from_request(LocalSessionStartRequest(headless=True, chrome_args=chrome_args))


def _launches(driver: MagicMock) -> list[tuple[bool, list[str]]]:
    return [(call.kwargs["chromium_sandbox"], call.kwargs["args"]) for call in driver.chromium.launch.await_args_list]


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux_user")
async def test_default_launch_keeps_the_chromium_sandbox(driver: MagicMock) -> None:
    _ = await lifecycle._launch_browser(driver, _options())  # pyright: ignore[reportPrivateUsage]

    [(sandbox, args)] = _launches(driver)
    assert sandbox is True
    assert not {"--no-sandbox", "--disable-setuid-sandbox", "--no-zygote"} & set(args)


@pytest.mark.asyncio
async def test_root_on_linux_launches_without_the_sandbox(driver: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lifecycle.sys, "platform", "linux")
    monkeypatch.setattr(lifecycle.os, "geteuid", lambda: 0, raising=False)

    _ = await lifecycle._launch_browser(driver, _options())  # pyright: ignore[reportPrivateUsage]

    assert [sandbox for sandbox, _ in _launches(driver)] == [False]


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux_user")
async def test_no_sandbox_chrome_arg_turns_the_sandbox_off(driver: MagicMock) -> None:
    _ = await lifecycle._launch_browser(driver, _options(["--no-sandbox"]))  # pyright: ignore[reportPrivateUsage]

    assert [sandbox for sandbox, _ in _launches(driver)] == [False]


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux_user")
@pytest.mark.parametrize(
    "message", [SANDBOX_FAILED, SUID_HELPER_MISCONFIGURED], ids=["no-usable-sandbox", "suid-helper"]
)
async def test_sandbox_failure_relaunches_without_the_sandbox(driver: MagicMock, message: str) -> None:
    browser = MagicMock(spec=Browser)
    driver.chromium.launch = AsyncMock(side_effect=[Error(message), browser])

    assert await lifecycle._launch_browser(driver, _options()) is browser  # pyright: ignore[reportPrivateUsage]

    assert [sandbox for sandbox, _ in _launches(driver)] == [True, False]


@pytest.mark.asyncio
@pytest.mark.usefixtures("linux_user")
async def test_other_launch_errors_are_not_retried(driver: MagicMock) -> None:
    driver.chromium.launch = AsyncMock(side_effect=Error("Browser.launch: Executable doesn't exist"))

    with pytest.raises(Error, match="Executable doesn't exist"):
        _ = await lifecycle._launch_browser(driver, _options())  # pyright: ignore[reportPrivateUsage]

    assert [sandbox for sandbox, _ in _launches(driver)] == [True]
