"""Payload/legacy-auth wire captures written before switching their requests."""

import base64
import hashlib
import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from notte_core import __version__
from notte_sdk import NotteClient
from notte_sdk.endpoints.run_payloads import offload_run_fields
from notte_sdk.errors import NotteAPIError

from tests.sdk.test_generated_endpoints import SERVER, fake
from tests.sdk.test_run_payloads import storage_session
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client
OPERATION = {
    "id": "operation",
    "connection_id": "connection",
    "source": "refresh",
    "status": "succeeded",
    "phase": "done",
    "deadline": "2026-10-13T00:00:00Z",
}


@pytest.mark.parametrize(
    "function_id,run_id,route",
    [("fn", "run", "/functions/fn/runs/run"), ("a/b ?#%é", "x/y", "/functions/a%2Fb%20%3F%23%25%C3%A9/runs/x%2Fy")],
)
def test_payload_upload_wire_contract(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, function_id: str, run_id: str, route: str
) -> None:
    fields = {"logs": ["some log"] * 20}
    raw = json.dumps(fields["logs"], ensure_ascii=False).encode()
    checksum = base64.b64encode(hashlib.sha256(raw).digest()).decode()
    reference = {"upload_id": "upload", "size_bytes": len(raw), "sha256": checksum}
    api = fake(monkeypatch, {"reference": reference, "url": "https://storage.example/object", "headers": {}})
    storage = storage_session(MagicMock(status_code=200))
    monkeypatch.setattr("notte_sdk.endpoints.run_payloads.requests.Session", lambda: storage)
    monkeypatch.setattr("notte_sdk.endpoints.run_payloads.INLINE_FIELD_BYTES", 1)
    result = offload_run_fields(client.functions, function_id, run_id, fields)
    assert result == {"payloads": {"logs": reference}}
    call = api.calls[0]
    assert (call.method, call.url, call.params) == (
        "POST",
        SERVER + route + "/payloads/logs/upload",
        None,
    )
    assert json.loads(call.data) == {"size_bytes": len(raw), "sha256": checksum}
    assert call.headers == {
        "Authorization": "Bearer test-api-key",  # pragma: allowlist secret
        "x-notte-sdk-version": __version__,
        "x-notte-request-origin": "sdk-python",
        "Content-Type": "application/json",
    }
    assert storage.put.call_args.kwargs["headers"] == {}
    assert storage.put.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("status", [404, 422])
def test_payload_api_errors(client: NotteClient, monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    api = fake(monkeypatch, {"detail": "upload failure"}, status)
    monkeypatch.setattr("notte_sdk.endpoints.run_payloads.INLINE_FIELD_BYTES", 1)
    with pytest.raises(NotteAPIError) as error:
        _ = offload_run_fields(client.functions, "fn", "run", {"logs": ["some log"]})
    assert error.value.status_code == status
    assert len(api.calls) == 1


def test_legacy_managed_auth_wire_contract(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(monkeypatch, {"connection_id": "connection", "status": "ok", "message": "ready"})
    assert client.managed_auth.check_connection("connection").authenticated is None
    api.payload = OPERATION
    assert client.managed_auth.get_operation("operation").status == "succeeded"
    assert client.managed_auth.refresh_connection("connection", wait=False).auth_retry == 0
    assert client.managed_auth.reauthenticate_connection("connection", auth_retry=2).status == "succeeded"
    assert [(c.method, c.url.removeprefix(SERVER), c.params) for c in api.calls] == [
        ("POST", "/managed-auth/connections/connection/check", None),
        ("GET", "/managed-auth/operations/operation", None),
        ("POST", "/managed-auth/connections/connection/refresh", None),
        ("POST", "/managed-auth/connections/connection/reauthenticate", None),
    ]
    assert [json.loads(c.data) for c in api.calls if c.method == "POST"] == [{}, {}, {"auth_retry": 2}]

    for call in api.calls:
        assert call.headers == {
            "Authorization": "Bearer test-api-key",  # pragma: allowlist secret
            "x-notte-sdk-version": __version__,
            "x-notte-request-origin": "sdk-python",
            **({"Content-Type": "application/json"} if call.method == "POST" else {}),
        }


@pytest.mark.parametrize("status", [404, 422])
@pytest.mark.parametrize(
    "method", ["check_connection", "get_operation", "refresh_connection", "reauthenticate_connection"]
)
def test_auth_api_errors(client: NotteClient, monkeypatch: pytest.MonkeyPatch, status: int, method: str) -> None:
    api = fake(monkeypatch, {"detail": "auth error"}, status)
    with pytest.raises(NotteAPIError) as error:
        _ = getattr(client.managed_auth, method)("owned-id")
    assert error.value.status_code == status
    assert error.value.error == {"detail": "auth error"}
    assert len(api.calls) == 1


@pytest.mark.parametrize("method", ["refresh_connection", "reauthenticate_connection"])
@pytest.mark.parametrize("auth_retry", [-1, 3, 0.5, None])
def test_auth_retry_is_validated_by_api(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, method: str, auth_retry: Any
) -> None:
    api = fake(monkeypatch, {"detail": "invalid auth_retry"}, 422)
    with pytest.raises(NotteAPIError) as error:
        _ = getattr(client.managed_auth, method)("connection", wait=False, auth_retry=auth_retry)
    assert error.value.status_code == 422
    assert json.loads(api.calls[0].data) == {"auth_retry": auth_retry}
