from types import SimpleNamespace

import notte_browser.window as window_module
import pytest
from notte_browser.errors import AkamaiSoftDenyExhaustedError
from notte_browser.navigation_recovery import AkamaiSoftDenyRecoveryPolicy, is_akamai_soft_deny
from notte_browser.window import BrowserWindow

AKAMAI_DENY_BODY = """
<html><body>
<h1>Access Denied</h1>
You don't have permission to access this page.
https://errors.edgesuite.net/18.example
</body></html>
"""
AKAMAI_DENY_HEADERS = {
    "Content-Type": "text/html; charset=utf-8",
    "X-Akamai-Transformed": "0 - 0 -",
}


class FakeResponse:
    def __init__(
        self,
        status: int,
        *,
        body: str = "",
        headers: dict[str, str] | None = None,
        url: str = "https://www.opentable.com/",
    ) -> None:
        self.status = status
        self.status_text = "OK" if status == 200 else "Forbidden"
        self.headers = headers or {"content-type": "text/html"}
        self.url = url
        self._body = body

    async def text(self) -> str:
        return self._body


class UnreadableResponse(FakeResponse):
    async def text(self) -> str:
        raise RuntimeError("response body unavailable")


class FakePage:
    def __init__(
        self,
        *,
        url: str = "https://www.opentable.com/",
        goto_response: FakeResponse | None = None,
        reload_responses: list[FakeResponse | None] | None = None,
    ) -> None:
        self.url = url
        self.goto_response = goto_response
        self.reload_responses = list(reload_responses or [])
        self.goto_calls: list[tuple[str, int]] = []
        self.reload_calls: list[int] = []
        self.wait_calls: list[int] = []
        self.default_timeout: int | None = None
        self.callbacks: dict[str, object] = {}

    def set_default_timeout(self, timeout: int) -> None:
        self.default_timeout = timeout

    def on(self, event: str, callback: object) -> None:
        self.callbacks[event] = callback

    def is_closed(self) -> bool:
        return False

    async def goto(self, url: str, *, timeout: int) -> FakeResponse | None:
        self.goto_calls.append((url, timeout))
        self.url = url
        return self.goto_response

    async def go_back(self, *, timeout: int) -> None:
        return None

    async def go_forward(self, *, timeout: int) -> None:
        return None

    async def reload(self, *, timeout: int) -> FakeResponse | None:
        self.reload_calls.append(timeout)
        return self.reload_responses.pop(0)

    async def wait_for_timeout(self, timeout: int) -> None:
        self.wait_calls.append(timeout)


def denied_response() -> FakeResponse:
    return FakeResponse(403, body=AKAMAI_DENY_BODY, headers=AKAMAI_DENY_HEADERS)


def make_window(page: FakePage) -> BrowserWindow:
    resource = SimpleNamespace(page=page)
    return BrowserWindow.model_construct(resource=resource, page_callbacks={})


@pytest.mark.parametrize(
    ("status", "headers", "body"),
    [
        (200, AKAMAI_DENY_HEADERS, AKAMAI_DENY_BODY),
        (403, {"content-type": "application/json", "x-akamai-transformed": "0 - 0 -"}, AKAMAI_DENY_BODY),
        (403, {"content-type": "text/html"}, AKAMAI_DENY_BODY),
        (403, AKAMAI_DENY_HEADERS, "Access Denied"),
    ],
)
def test_akamai_soft_deny_detector_rejects_incomplete_signatures(
    status: int, headers: dict[str, str], body: str
) -> None:
    assert not is_akamai_soft_deny(status=status, headers=headers, body=body)


def test_akamai_soft_deny_detector_matches_captured_signature() -> None:
    assert is_akamai_soft_deny(status=403, headers=AKAMAI_DENY_HEADERS, body=AKAMAI_DENY_BODY)


def test_akamai_recovery_policy_validates_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AKAMAI_SOFT_DENY_RECOVERY_ENABLED", "yes")
    monkeypatch.setenv("AKAMAI_SOFT_DENY_MAX_RELOADS", "5")
    monkeypatch.setenv("AKAMAI_SOFT_DENY_SETTLE_MS", "500")

    assert AkamaiSoftDenyRecoveryPolicy.from_env() == AkamaiSoftDenyRecoveryPolicy(
        enabled=True,
        max_reloads=5,
        settle_ms=500,
    )

    monkeypatch.setenv("AKAMAI_SOFT_DENY_MAX_RELOADS", "6")
    with pytest.raises(ValueError, match="AKAMAI_SOFT_DENY_MAX_RELOADS must be between 0 and 5"):
        AkamaiSoftDenyRecoveryPolicy.from_env()


@pytest.mark.asyncio
async def test_recovery_reloads_same_page_until_success(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = AkamaiSoftDenyRecoveryPolicy(enabled=True, max_reloads=3, settle_ms=750)
    monkeypatch.setattr(window_module, "AKAMAI_SOFT_DENY_RECOVERY_POLICY", policy)
    successful_response = FakeResponse(200, body="OpenTable")
    page = FakePage(reload_responses=[denied_response(), successful_response])
    window = make_window(page)

    result = await window._recover_akamai_soft_deny(page.url, denied_response())  # pyright: ignore[reportPrivateUsage]

    assert result is successful_response
    assert window.goto_response is successful_response
    assert page.wait_calls == [750, 750]
    assert len(page.reload_calls) == 2
    assert window.page is page


@pytest.mark.asyncio
async def test_recovery_is_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = AkamaiSoftDenyRecoveryPolicy(enabled=False, max_reloads=3, settle_ms=750)
    monkeypatch.setattr(window_module, "AKAMAI_SOFT_DENY_RECOVERY_POLICY", policy)
    initial_response = denied_response()
    page = FakePage(reload_responses=[FakeResponse(200)])
    window = make_window(page)

    result = await window._recover_akamai_soft_deny(page.url, initial_response)  # pyright: ignore[reportPrivateUsage]

    assert result is initial_response
    assert page.wait_calls == []
    assert page.reload_calls == []


@pytest.mark.asyncio
async def test_recovery_is_fail_open_when_response_body_is_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = AkamaiSoftDenyRecoveryPolicy(enabled=True, max_reloads=3, settle_ms=750)
    monkeypatch.setattr(window_module, "AKAMAI_SOFT_DENY_RECOVERY_POLICY", policy)
    initial_response = UnreadableResponse(403, headers=AKAMAI_DENY_HEADERS)
    page = FakePage(reload_responses=[FakeResponse(200)])
    window = make_window(page)

    result = await window._recover_akamai_soft_deny(page.url, initial_response)  # pyright: ignore[reportPrivateUsage]

    assert result is initial_response
    assert page.wait_calls == []
    assert page.reload_calls == []


@pytest.mark.asyncio
async def test_recovery_raises_retryable_error_when_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = AkamaiSoftDenyRecoveryPolicy(enabled=True, max_reloads=3, settle_ms=500)
    monkeypatch.setattr(window_module, "AKAMAI_SOFT_DENY_RECOVERY_POLICY", policy)
    page = FakePage(reload_responses=[denied_response(), denied_response(), denied_response()])
    window = make_window(page)

    with pytest.raises(AkamaiSoftDenyExhaustedError) as exc_info:
        await window._recover_akamai_soft_deny(page.url, denied_response())  # pyright: ignore[reportPrivateUsage]

    assert exc_info.value.should_retry_later
    assert page.wait_calls == [500, 500, 500]
    assert len(page.reload_calls) == 3


@pytest.mark.asyncio
async def test_goto_retries_same_url_after_soft_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = AkamaiSoftDenyRecoveryPolicy(enabled=True, max_reloads=3, settle_ms=500)
    monkeypatch.setattr(window_module, "AKAMAI_SOFT_DENY_RECOVERY_POLICY", policy)
    page = FakePage(goto_response=FakeResponse(200, body="OpenTable"))
    window = make_window(page)
    window.goto_response = denied_response()  # pyright: ignore[reportAttributeAccessIssue]

    await window.goto(page.url)

    assert len(page.goto_calls) == 1


@pytest.mark.asyncio
async def test_goto_keeps_same_url_noop_for_normal_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = AkamaiSoftDenyRecoveryPolicy(enabled=True, max_reloads=3, settle_ms=500)
    monkeypatch.setattr(window_module, "AKAMAI_SOFT_DENY_RECOVERY_POLICY", policy)
    page = FakePage(goto_response=FakeResponse(200, body="OpenTable"))
    window = make_window(page)
    window.goto_response = FakeResponse(200, body="OpenTable")  # pyright: ignore[reportAttributeAccessIssue]

    await window.goto(page.url)

    assert page.goto_calls == []
