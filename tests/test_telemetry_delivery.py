from typing import Any

import pytest
from notte_core import telemetry


def test_track_usage_delivers_metadata_only_to_telemetry_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    posthog_events: list[tuple[str, str, dict[str, Any]]] = []
    scarf_events: list[dict[str, Any]] = []

    class RecordingPosthogClient:
        def capture(self, *, distinct_id: str, event: str, properties: dict[str, Any]) -> None:
            posthog_events.append((distinct_id, event, properties.copy()))

    class RecordingScarfClient:
        def log_event(self, *, properties: dict[str, Any]) -> None:
            scarf_events.append(properties.copy())

    monkeypatch.setattr(telemetry, "DISABLE_TELEMETRY", False)
    monkeypatch.setattr(telemetry, "get_system_info", lambda: {})
    clients = (RecordingPosthogClient(), RecordingScarfClient(), "test-installation")
    monkeypatch.setattr(telemetry, "_clients", lambda: clients)

    secret = "delivery-boundary-secret"  # noqa: S105  # pragma: allowlist secret

    @telemetry.track_usage("test.delivery_boundary")
    def decorated(*, api_token: str) -> None:
        raise RuntimeError(f"request failed with {api_token}")

    with pytest.raises(RuntimeError, match=secret):
        decorated(api_token=secret)

    assert posthog_events == [
        (
            "test-installation",
            "test.delivery_boundary",
            {
                "status": "error",
                "error_type": "RuntimeError",
                "process_person_profile": True,
            },
        )
    ]
    # PostHog-only settings such as `process_person_profile` stay out of the Scarf payload.
    assert scarf_events == [
        {
            "status": "error",
            "error_type": "RuntimeError",
            "event": "test.delivery_boundary",
            "installation_id": "test-installation",
        }
    ]
    assert secret not in repr(posthog_events)
    assert secret not in repr(scarf_events)


def test_real_posthog_client_accepts_the_telemetry_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the installed client's constructor and event builder without delivery."""
    import posthog
    from posthog.client import Client

    captured: list[dict[str, Any]] = []

    def enqueue(self: Client, message: dict[str, Any], *args: Any, **kwargs: Any) -> tuple[bool, dict[str, Any]]:
        _ = self, args, kwargs
        captured.append(message)
        return True, message

    # Replacing enqueue prevents consumer threads and network I/O while leaving
    # the real constructor, capture signature and event normalization intact.
    monkeypatch.setattr(Client, "_enqueue", enqueue)
    monkeypatch.setattr(telemetry, "DISABLE_TELEMETRY", False)
    monkeypatch.setattr(telemetry, "POSTHOG_API_KEY", "test-project-key")
    client = telemetry.setup_posthog()
    assert isinstance(client, posthog.Posthog)
    try:
        client.capture(distinct_id="test-installation", event="compatibility", properties={"status": "success"})
        assert captured[0]["event"] == "compatibility"
        assert captured[0]["distinct_id"] == "test-installation"
        assert captured[0]["properties"]["status"] == "success"
    finally:
        client.shutdown()
