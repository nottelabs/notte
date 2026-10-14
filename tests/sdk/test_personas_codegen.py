"""Persona wire captures first run before replacing the core-bound facade."""

import datetime as dt
import json

import pytest
from notte_core import __version__
from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import EmailResponse, PersonaResponse, SMSResponse

from tests.sdk.test_generated_endpoints import PERSONA, SERVER, fake
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client

ID = "a/b ?#%é"
PATH = "/personas/a%2Fb%20%3F%23%25%C3%A9"
EMAIL = {
    "subject": "Hello",
    "email_id": "email-1",
    "created_at": "2026-10-13T00:00:00Z",
    "sender_email": None,
    "sender_name": None,
}
SMS = {"body": "Hello", "sms_id": "sms-1", "created_at": "2026-10-13T00:00:00Z", "sender": None}


def test_persona_wire_contract(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    monkeypatch.setattr("notte_core.common.telemetry._capture_usage_event", lambda name, **_: events.append(name))
    session = fake(monkeypatch, PERSONA)
    assert isinstance(client.personas.create(name=None), PersonaResponse)
    _ = client.personas.create(create_vault=True, name="Ada")
    assert client.personas.get(ID).name is None
    session.payload = {"items": [PERSONA], "page": 1, "page_size": 10, "total": 1}
    assert len(client.personas.list()) == 1
    session.payload = []
    assert client.personas.list(page=0, page_size=101, only_active=False) == []
    session.payload = [EMAIL]
    assert isinstance(client.personas.emails_list(ID)[0], EmailResponse)
    _ = client.personas.emails_list(ID, limit=3, timedelta=dt.timedelta(minutes=5), only_unread=True)
    session.payload = [SMS]
    assert isinstance(client.personas.sms_list(ID)[0], SMSResponse)
    _ = client.personas.sms_list(ID, limit=2, timedelta=dt.timedelta(seconds=30))
    session.payload = {"phone_number": "+1555", "status": "success"}
    assert client.personas.create_number(ID).phone_number == "+1555"
    session.payload = {"status": "failure"}
    assert client.personas.delete_number(ID).message == "Phone number deleted successfully"
    assert client.personas.delete(ID).status == "failure"
    assert [(c.method, c.url.removeprefix(SERVER), c.params) for c in session.calls] == [
        ("POST", "/personas/create", None),
        ("POST", "/personas/create", None),
        ("GET", PATH, None),
        ("GET", "/personas", {}),
        ("GET", "/personas", {"only_active": False, "page_size": 101, "page": 0}),
        ("GET", PATH + "/emails", {}),
        ("GET", PATH + "/emails", {"limit": 3, "timedelta": dt.timedelta(minutes=5), "only_unread": True}),
        ("GET", PATH + "/sms", {}),
        ("GET", PATH + "/sms", {"limit": 2, "timedelta": dt.timedelta(seconds=30)}),
        ("POST", PATH + "/sms/number", None),
        ("DELETE", PATH + "/sms/number", None),
        ("DELETE", PATH, None),
    ]
    assert [json.loads(c.data) for c in session.calls if c.method == "POST"] == [
        {},
        {"create_vault": True, "name": "Ada"},
        {},
    ]
    for call in session.calls:
        assert call.headers == {
            "Authorization": "Bearer test-api-key",  # pragma: allowlist secret
            "x-notte-sdk-version": __version__,
            "x-notte-request-origin": "sdk-python",
            **({"Content-Type": "application/json"} if call.method == "POST" else {}),
        }
    assert events == [
        "cloud.personas." + name
        for name in [
            "create",
            "create",
            "get",
            "emails.list",
            "emails.list",
            "sms.list",
            "sms.list",
            "create_number",
            "delete_number",
            "delete",
        ]
    ]


@pytest.mark.parametrize("status", [404, 422])
@pytest.mark.parametrize(
    "method", ["create", "get", "list", "delete", "emails_list", "sms_list", "create_number", "delete_number"]
)
def test_persona_errors(client: NotteClient, monkeypatch: pytest.MonkeyPatch, status: int, method: str) -> None:
    session = fake(monkeypatch, {"detail": "persona error"}, status_code=status)
    with pytest.raises(NotteAPIError) as error:
        _ = getattr(client.personas, method)(*(() if method in {"create", "list"} else (ID,)))
    assert error.value.status_code == status
    assert error.value.error == {"detail": "persona error"}
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "text,links",
    [
        (None, []),
        ("", []),
        ("[go](https://example.com/a) https://example.com/b", ["https://example.com/a", "https://example.com/b"]),
    ],
)
def test_email_links_and_defaults(text: str | None, links: list[str]) -> None:
    email = EmailResponse.model_validate({**EMAIL, "text_content": text})
    assert email.links() == links
    assert email.html_content is None


def test_persona_helper_constructor_defaults(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    session = fake(monkeypatch, PERSONA)
    persona = client.Persona(create_vault=True)
    assert persona.email == PERSONA["email"]
    assert json.loads(session.calls[-1].data) == {"create_vault": True}


@pytest.mark.parametrize("helper", [False, True])
def test_persona_invalid_input_reaches_api(client: NotteClient, monkeypatch: pytest.MonkeyPatch, helper: bool) -> None:
    session = fake(monkeypatch, {"detail": "invalid create_vault"}, status_code=422)
    with pytest.raises(NotteAPIError) as error:
        if helper:
            _ = client.Persona(create_vault="invalid")  # pyright: ignore[reportArgumentType]
        else:
            _ = client.personas.create(create_vault="invalid")  # pyright: ignore[reportArgumentType]
    assert error.value.status_code == 422
    assert json.loads(session.calls[-1].data)["create_vault"] == "invalid"


def test_persona_types_are_generated() -> None:
    from notte_sdk import types
    from notte_sdk._generated import models

    assert types.PersonaCreateRequest is models.PersonaCreateRequest
    assert types.PersonaResponse is models.PersonaResponse
    assert types.SMSResponse is models.SMSResponse
    assert types.MessageReadRequest is models.PersonaEmailsListParametersQuery
    from notte_core.types import EmailResponse as CoreEmailResponse

    assert types.EmailResponse is CoreEmailResponse
    from notte_core.types import PersonaListRequest as CorePersonaListRequest

    assert types.PersonaListRequest is CorePersonaListRequest
