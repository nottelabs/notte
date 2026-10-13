import io
import json
from unittest.mock import MagicMock

import pytest
import requests
from notte_core.common.logging import logger
from notte_sdk.endpoints import workflows
from notte_sdk.endpoints.base import BaseClient
from notte_sdk.endpoints.sessions import SessionsClient
from notte_sdk.endpoints.workflows import WorkflowsClient


@pytest.mark.parametrize("key_source", ["argument", "environment"])
@pytest.mark.parametrize("explicit_stream", [False, True])
@pytest.mark.parametrize("viewer_state", ["jwt", "missing", "error", "timeout", "legacy_api_key"])
def test_session_start_does_not_log_api_key(monkeypatch, key_source, explicit_stream, viewer_state):
    api_key = "test-only-secret-function-stream-key"  # pragma: allowlist secret
    session_id = "session-123"
    monkeypatch.setenv("NOTTE_API_KEY", api_key)
    monkeypatch.setattr(BaseClient, "check_and_warn_version_mismatch", lambda self: None)
    root_client = MagicMock()
    viewer_url = (
        f"https://console.notte.cc/static/viewer?ws=wss://us-prod.notte.cc/sessions/{session_id}/debug/recording"
        "&jwt=fake-session-jwt"
    )
    match viewer_state:
        case "jwt":
            root_client.sessions.request.return_value.viewer_url = viewer_url
        case "missing":
            root_client.sessions.request.return_value.viewer_url = None
        case "error":
            root_client.sessions.request.side_effect = requests.ConnectionError(f"Request failed: {api_key}")
        case "timeout":
            root_client.sessions.request.side_effect = requests.Timeout(f"Request timed out: {api_key}")
        case "legacy_api_key":
            root_client.sessions.request.return_value.viewer_url = viewer_url.replace(
                "&jwt=fake-session-jwt", f"?token={api_key}"
            )
    client = WorkflowsClient(
        root_client=root_client,
        api_key=api_key if key_source == "argument" else None,
        server_url="https://example.invalid",
    )
    result = {
        "function_id": "function-123",
        "function_run_id": "run-123",
        "session_id": session_id,
        "status": "closed",
        "result": {"ok": True},
    }
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_lines.return_value = [
        ("data: " + json.dumps(event)).encode()
        for event in [
            {"type": "session_start", "message": session_id},
            {"type": "log", "message": "Function is running"},
            {"type": "result", "message": json.dumps(result)},
        ]
    ]
    post = MagicMock(return_value=response)
    monkeypatch.setattr(workflows.requests, "post", post)
    captured = io.StringIO()
    handler = logger.add(captured, level="INFO")
    try:
        completed = client.run(
            "run-123", function_id="function-123", variables={}, **({"stream": True} if explicit_stream else {})
        )
    finally:
        logger.remove(handler)

    output = captured.getvalue()
    assert api_key not in output
    assert "?token=" not in output
    assert session_id in output
    if viewer_state == "jwt":
        assert viewer_url in output
    else:
        assert "client.sessions.viewer" in output
    root_client.sessions.request.assert_called_once_with(
        SessionsClient._session_status_endpoint(session_id=session_id), timeout=2
    )
    assert "Function is running" in output
    assert completed.session_id == session_id
    assert completed.result == {"ok": True}
    assert post.call_args.kwargs["headers"]["Authorization"] == f"Bearer {api_key}"
    assert post.call_args.kwargs["headers"]["x-notte-api-key"] == api_key
