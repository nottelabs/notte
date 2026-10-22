"""Transport boundaries for the complete shared resource inventory."""

import json
from typing import Any

import pytest
from notte_core import types as core
from notte_sdk import NotteClient, types
from notte_sdk._generated.typing import PaymentRequestDict, SessionProfileSaveRequestDict
from notte_sdk.errors import NotteAPIError

from tests.sdk.test_generated_endpoints import SERVER, fake
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client


def test_core_behavior_types_retain_identity() -> None:
    for name in (
        "SessionStartRequest",
        "SessionResponse",
        "Cookie",
        "SessionProfile",
        "NotteProxy",
        "ExternalProxy",
        "GetCredentialsResponse",
        "GetCookiesResponse",
        "ReplayResponse",
        "SessionDebugResponse",
    ):
        assert getattr(types, name) is getattr(core, name)


def test_combined_body_query_and_required_header(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    transport = fake(monkeypatch, {"detail": "invalid payment"}, 422)
    data: dict[str, Any] = {"unexpected": "sent to server"}
    with pytest.raises(NotteAPIError):
        client.sessions.create_payment("s/id", idempotency_key="unique", query={"update_metadata": False}, **data)
    call = transport.calls[0]
    assert call.url == SERVER + "/sessions/s%2Fid/payments"
    assert call.headers["idempotency-key"] == "unique"
    assert call.params == {"update_metadata": "False"}
    assert json.loads(call.data) == data


@pytest.mark.parametrize("payload", [[1, 2], "detail text", {"key": True}, {"detail": "notes"}, None])
def test_untyped_run_payload_retains_json_shape(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    transport = fake(monkeypatch, payload)
    assert client.functions.download_run_payload("f/id", "r/id", "result") == payload
    assert transport.calls[0].url == SERVER + "/functions/f%2Fid/runs/r%2Fid/payloads/result"


def test_profile_preview_keeps_core_profile(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, {"profile": {"id": "profile-id"}, "cookie_domains": []})
    assert isinstance(client.sessions.profile_preview("session").profile, core.SessionProfile)


def test_untyped_payload_keeps_http_errors(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, {"detail": "missing payload"}, 404)
    with pytest.raises(NotteAPIError) as error:
        client.functions.download_run_payload("function", "run", "variables")
    assert error.value.status_code == 404


def test_primitive_keyword_inputs_typecheck() -> None:
    # These assignments also run through pinned basedpyright; callers do not
    # need private generated RootModel wrappers around primitive JSON values.
    profile: SessionProfileSaveRequestDict = {"name": "saved", "profile_id": "id"}
    payment: PaymentRequestDict = {
        "amount": "100.91",
        "currency": "USD",
        "merchant_url": "https://example.test",
        "merchant_name": "Example",
        "description": "test",
    }
    payment["amount"] = 100.91
    assert profile["name"] == "saved"
    assert payment["amount"] == 100.91
