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
        password="password-secret",  # pragma: allowlist secret
        card_number="card-number-secret",
        card_cvv="card-cvv-secret",
        api_token="api-token-secret",
    )

    assert result == "ok"
    assert events == [("test.success", {"status": "success"})]
    assert all(secret not in repr(events) for secret in sensitive_values)


def test_track_usage_does_not_capture_exception_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    events = capture_usage_events(monkeypatch)
    secret = "exception-secret"  # pragma: allowlist secret

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
    secret = "async-secret"  # pragma: allowlist secret

    @telemetry.track_usage("test.async_error")
    async def decorated(*, token: str) -> None:
        raise ValueError(f"request failed with {token}")

    coroutine = decorated(token=secret)
    assert events == []

    with pytest.raises(ValueError, match=secret):
        await coroutine

    assert events == [("test.async_error", {"status": "error", "error_type": "ValueError"})]
    assert secret not in repr(events)
