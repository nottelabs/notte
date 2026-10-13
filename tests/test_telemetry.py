import subprocess
import sys
from typing import Any

import pytest
from notte_core.common import telemetry


def capture_usage_events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any] | None]]:
    events: list[tuple[str, dict[str, Any] | None]] = []

    def capture_event(event_name: str, properties: dict[str, Any] | None = None) -> None:
        events.append((event_name, properties))

    monkeypatch.setattr(telemetry, "capture_event", capture_event)
    return events


def test_track_usage_does_not_capture_argument_values(monkeypatch: pytest.MonkeyPatch) -> None:
    events = capture_usage_events(monkeypatch)
    sensitive_values = {
        "positional-secret",
        "password-secret",
        "card-number-secret",
        "card-cvv-secret",
        "api-token-secret",
    }

    @telemetry.track_usage("test.success")
    def decorated(positional_value: str, **kwargs: str) -> str:
        assert positional_value in sensitive_values
        assert kwargs
        return "ok"

    result = decorated(
        "positional-secret",
        password="password-secret",  # noqa: S106  # pragma: allowlist secret
        card_number="card-number-secret",
        card_cvv="card-cvv-secret",
        api_token="api-token-secret",  # noqa: S106  # pragma: allowlist secret
    )

    assert result == "ok"
    assert events == [("test.success", {"status": "success"})]
    assert all(secret not in repr(events) for secret in sensitive_values)


def test_track_usage_does_not_capture_exception_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    events = capture_usage_events(monkeypatch)
    secret = "exception-secret"  # noqa: S105  # pragma: allowlist secret

    @telemetry.track_usage("test.error")
    def decorated() -> None:
        raise RuntimeError(f"request failed with {secret}")

    with pytest.raises(RuntimeError, match=secret):
        decorated()

    assert events == [("test.error", {"status": "error", "error_type": "RuntimeError"})]
    assert secret not in repr(events)


@pytest.mark.asyncio
async def test_track_usage_captures_async_failures_after_await(monkeypatch: pytest.MonkeyPatch) -> None:
    events = capture_usage_events(monkeypatch)
    secret = "async-secret"  # noqa: S105  # pragma: allowlist secret

    @telemetry.track_usage("test.async_error")
    async def decorated(*, token: str) -> None:
        raise ValueError(f"request failed with {token}")

    coroutine = decorated(token=secret)
    assert events == []

    with pytest.raises(ValueError, match=secret):
        await coroutine

    assert events == [("test.async_error", {"status": "error", "error_type": "ValueError"})]
    assert secret not in repr(events)


def test_importing_the_sdk_does_not_start_telemetry() -> None:
    """Telemetry clients (and their imports) are only created on the first captured event."""
    code = (
        "import sys, notte_sdk, notte_core.common.telemetry as t\n"
        "assert 'posthog' not in sys.modules and 'scarf' not in sys.modules, sorted(sys.modules)\n"
        "assert t._clients.cache_info().currsize == 0\n"
    )
    _ = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


@pytest.mark.asyncio
async def test_reading_the_session_snapshot_is_not_a_usage_event(monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_browser.session import NotteSession

    async with NotteSession(headless=True) as session:
        _ = await session.window.page.goto("data:text/html,<button>Go</button>")
        events = capture_usage_events(monkeypatch)
        _ = await session.aobserve()
        _ = session.snapshot

    names = [name for name, _ in events]
    assert "local.session.snapshot" not in names
    assert names.count("local.session.observe") == 1


def test_capture_event_copies_properties_per_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, dict[str, Any]] = {}

    class PostHog:
        def capture(self, *, distinct_id: str, event: str, properties: dict[str, Any]) -> None:
            sent["posthog"] = properties

    class Scarf:
        def log_event(self, *, properties: dict[str, Any]) -> None:
            sent["scarf"] = properties

    monkeypatch.setattr(telemetry, "DISABLE_TELEMETRY", False)
    monkeypatch.setattr(telemetry, "_clients", lambda: (PostHog(), Scarf(), "installation"))
    properties: dict[str, Any] = {"status": "success"}

    telemetry.capture_event("test.event", properties=properties)

    assert properties == {"status": "success"}
    assert set(telemetry.POSTHOG_EVENT_SETTINGS) <= set(sent["posthog"])
    assert not set(telemetry.POSTHOG_EVENT_SETTINGS) & set(sent["scarf"])
    assert sent["scarf"]["event"] == "test.event"
    assert "event" not in sent["posthog"]
