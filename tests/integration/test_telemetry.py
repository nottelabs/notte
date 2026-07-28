from typing import Any

import pytest
from notte_core.common import telemetry


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
    monkeypatch.setattr(telemetry, "INSTALLATION_ID", "test-installation")
    monkeypatch.setattr(telemetry, "get_system_info", lambda: {})
    monkeypatch.setattr(telemetry, "posthog_client", RecordingPosthogClient())
    monkeypatch.setattr(telemetry, "scarf_client", RecordingScarfClient())

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
    assert scarf_events == [
        {
            "status": "error",
            "error_type": "RuntimeError",
            "process_person_profile": True,
            "event": "test.delivery_boundary",
            "installation_id": "test-installation",
        }
    ]
    assert secret not in repr(posthog_events)
    assert secret not in repr(scarf_events)
