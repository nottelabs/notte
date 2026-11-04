"""Deleting a function must be confirmed, and protection is one call away."""

import json

import pytest
from notte_sdk import NotteClient

from tests.sdk.test_generated_endpoints import fake
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client
STAMP = "2026-11-04T00:00:00Z"
FUNCTION = dict(
    function_id="fn", created_at=STAMP, updated_at=STAMP, latest_version="v1", versions=["v1"], status="active"
)


@pytest.mark.parametrize("kwargs", [{}, {"confirm": False}])
def test_delete_without_confirmation_sends_nothing(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, bool]
) -> None:
    api = fake(monkeypatch, FUNCTION)
    function = client.Function("fn")

    with pytest.raises(ValueError, match=r"delete\(confirm=True\)"):
        function.delete(**kwargs)

    assert api.calls == []


def test_delete_with_confirmation_deletes(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = fake(monkeypatch, {**FUNCTION, "url": "https://storage.example/code"})
    function = client.Function("fn")
    assert function.response.function_id == "fn"
    api.payload = {"status": "success", "message": "gone"}

    function.delete(confirm=True)

    assert (api.calls[-1].method, api.calls[-1].url.rsplit("/", 2)[-2:]) == ("DELETE", ["functions", "fn"])


def test_low_level_delete_is_not_asked_to_confirm(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = fake(monkeypatch, {"status": "success", "message": "gone"})

    assert client.functions.delete("fn").status == "success"


@pytest.mark.parametrize("enabled", [True, False])
def test_set_deletion_protection_updates_the_function(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    api = fake(monkeypatch, {**FUNCTION, "deletion_protected": enabled})
    function = client.Function("fn")

    function.set_deletion_protection(enabled)

    assert [(call.method, json.loads(call.data)) for call in api.calls] == [("PATCH", {"deletion_protected": enabled})]
    assert function.response.deletion_protected is enabled
    assert len(api.calls) == 1


def test_a_response_without_the_field_reads_as_unprotected(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = fake(monkeypatch, {**FUNCTION, "url": "https://storage.example/code"})

    assert client.Function("fn").response.deletion_protected is False
