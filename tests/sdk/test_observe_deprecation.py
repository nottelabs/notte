"""`observe(instructions=...)` and `perception_type='deep'` warn before their removal on December 1, 2026."""

import warnings
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from notte_core.observation import Observation
from notte_sdk.client import NotteClient
from notte_sdk.endpoints.page import PageClient
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.types import ObserveRequest

SESSION_ID = "observe-deprecation-session"


@pytest.fixture
def client() -> NotteClient:
    return NotteClient(api_key="test-api-key")  # pragma: allowlist secret


@pytest.fixture
def sent() -> Any:
    with patch.object(PageClient, "request", return_value=Observation.empty()) as request:
        yield request


def _session(client: NotteClient, **options: Any) -> RemoteSession:
    with patch.object(type(client.sessions), "status", return_value=MagicMock(session_id=SESSION_ID)):
        return RemoteSession(SESSION_ID, _client=client.sessions, **options)


def _observe_warnings(observe: Any, **data: Any) -> list[warnings.WarningMessage]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _ = observe(**data)
    return [warning for warning in caught if issubclass(warning.category, DeprecationWarning)]


def test_instructions_warn_with_the_removal_date(client: NotteClient, sent: MagicMock) -> None:
    [warning] = _observe_warnings(client.sessions.page.observe, session_id=SESSION_ID, instructions="click login")

    message = str(warning.message)
    assert "`observe(instructions=...)` is deprecated and will be removed on December 1, 2026" in message
    assert "pick from the returned actions yourself" in message
    assert "https://docs.notte.cc/features/sessions/observe-migration" in message
    # The default filters show a DeprecationWarning only when it is attributed to the caller's code.
    assert warning.filename == __file__
    # The request is still sent as before.
    endpoint = sent.call_args.args[0]
    assert endpoint.request.instructions == "click login"


def test_deep_perception_warns_with_the_fast_alternative(client: NotteClient, sent: MagicMock) -> None:
    _ = sent
    [warning] = _observe_warnings(client.sessions.page.observe, session_id=SESSION_ID, perception_type="deep")

    message = str(warning.message)
    assert "`perception_type='deep'` is deprecated and will be removed on December 1, 2026" in message
    assert "use `perception_type='fast'` (the default)" in message
    assert warning.filename == __file__


def test_both_options_warn_once_each(client: NotteClient, sent: MagicMock) -> None:
    _ = sent
    caught = _observe_warnings(
        client.sessions.page.observe, session_id=SESSION_ID, instructions="click login", perception_type="deep"
    )
    assert len(caught) == 2


@pytest.mark.parametrize("data", [{}, {"perception_type": "fast"}, {"perception_type": None, "instructions": None}])
def test_fast_observes_do_not_warn(client: NotteClient, sent: MagicMock, data: dict[str, Any]) -> None:
    _ = sent
    assert _observe_warnings(client.sessions.page.observe, session_id=SESSION_ID, **data) == []


def test_session_observe_attributes_the_warning_to_the_caller(client: NotteClient, sent: MagicMock) -> None:
    _ = sent
    session = _session(client)
    [warning] = _observe_warnings(session.observe, instructions="click login")
    assert warning.filename == __file__


def test_a_deep_session_default_warns_on_observe(client: NotteClient, sent: MagicMock) -> None:
    session = _session(client, perception_type="deep")
    [warning] = _observe_warnings(session.observe)
    assert "perception_type='deep'" in str(warning.message)
    assert sent.call_args.args[0].request.perception_type == "deep"


def test_fast_session_observe_does_not_warn(client: NotteClient, sent: MagicMock) -> None:
    _ = sent
    assert _observe_warnings(_session(client).observe) == []


def test_instructions_are_deprecated_in_the_request_schema() -> None:
    # A request body: the API publishes its validation schema.
    properties = ObserveRequest.model_json_schema(mode="validation")["properties"]
    assert properties["instructions"]["deprecated"] is True
    assert "December 1, 2026" in properties["instructions"]["description"]
    assert "December 1, 2026" in properties["perception_type"]["description"]
    # Reading a field never warns: only callers that set it are told.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert ObserveRequest().instructions is None
