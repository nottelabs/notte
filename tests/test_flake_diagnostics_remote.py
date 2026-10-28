"""Remote diagnostics stay bounded and cannot bypass the session's original exit."""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from notte_core.observation import Observation
from notte_sdk import NotteClient
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.types import SessionResponse

from tests import flake_diagnostics
from tests.mock.snapshot_factory import make_snapshot
from tests.sdk.test_generated_endpoints import SERVER, fake
from tests.sdk.test_sessions_codegen import SESSION


@pytest.fixture
def retained_remote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[flake_diagnostics.Diagnostics, RemoteSession, MagicMock, MagicMock]]:
    original_exit = MagicMock()
    original_scrape = MagicMock(return_value="public page")
    monkeypatch.setattr(RemoteSession, "__exit__", original_exit)
    monkeypatch.setattr(RemoteSession, "scrape", original_scrape)
    item = MagicMock(spec=pytest.Item)
    item.nodeid = "tests/integration/sdk/test_scraping.py::test_sdk_scraping_markdown"
    item.stash = pytest.Stash()
    item.config = MagicMock()
    item.config.rootpath = tmp_path
    item.execution_count = 1
    request = MagicMock(spec=pytest.FixtureRequest)
    request.node = item
    request.getfixturevalue.return_value = monkeypatch
    fixture = flake_diagnostics.retain_flake_diagnostics.__wrapped__(request)
    next(fixture)

    session = MagicMock(spec=RemoteSession)
    session.session_id = "fixture-session"
    session.response = MagicMock(status="active", close_reason=None, error=None)
    session.client = MagicMock()
    session.client.root_client.max_retries = 3
    observed = Observation.empty().model_copy(deep=True)
    observed.metadata = make_snapshot("https://www.notte.cc").metadata
    session.client.page.request.return_value = observed
    yield item.stash[flake_diagnostics._STATE], session, original_exit, original_scrape
    fixture.close()


def test_successful_scrape_uses_cached_metadata_without_diagnostic_request(retained_remote) -> None:
    diagnostics, session, original_exit, original_scrape = retained_remote
    result = RemoteSession.scrape(session)
    assert result is original_scrape.return_value
    RemoteSession.__exit__(session, None, None, None)
    session.client.page.request.assert_not_called()
    session.observe.assert_not_called()
    session.status.assert_not_called()
    original_exit.assert_called_once_with(session, None, None, None)
    assert json.loads(diagnostics.files["session.json"])["status"] == "active"
    assert "observation.txt" not in diagnostics.files


def test_result_inspection_interrupt_does_not_change_scrape_result(retained_remote) -> None:
    diagnostics, session, original_exit, original_scrape = retained_remote

    class UnreadableText(str):
        def __len__(self) -> int:
            raise KeyboardInterrupt("diagnostic length interrupted")

    result = UnreadableText("public page")
    original_scrape.return_value = result
    assert RemoteSession.scrape(session) is result
    RemoteSession.__exit__(session, None, None, None)
    original_exit.assert_called_once_with(session, None, None, None)
    session.client.page.request.assert_not_called()
    assert "diagnostic length interrupted" in diagnostics.files["scrape-result.capture-error.txt"]


@pytest.mark.parametrize("result", ["", {"unexpected": "structured response"}])
def test_invalid_scrape_result_is_unchanged_and_captured_before_cleanup(retained_remote, result) -> None:
    diagnostics, session, original_exit, original_scrape = retained_remote
    original_scrape.return_value = result
    observed = session.client.page.request.return_value

    def observe(endpoint, *, timeout):
        assert endpoint.path == "/sessions/fixture-session/page/observe"
        assert timeout == flake_diagnostics._REMOTE_CAPTURE_TIMEOUT_SECONDS
        assert session.client.root_client.max_retries == 0
        original_exit.assert_not_called()
        return observed

    session.client.page.request.side_effect = observe
    returned = RemoteSession.scrape(session)
    assert returned is result
    RemoteSession.__exit__(session, None, None, None)
    assert "observation.txt" in diagnostics.files
    session.client.page.request.assert_called_once()
    assert session.client.root_client.max_retries == 3
    original_exit.assert_called_once_with(session, None, None, None)


@pytest.mark.parametrize("capture_error", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
def test_diagnostic_interrupt_preserves_original_error_and_guarantees_cleanup(retained_remote, capture_error) -> None:
    diagnostics, session, original_exit, _ = retained_remote
    original_error = ValueError("original scrape failure")
    session.client.page.request.side_effect = capture_error("diagnostic interrupted")
    RemoteSession.__exit__(session, ValueError, original_error, None)
    assert session.client.root_client.max_retries == 3
    original_exit.assert_called_once_with(session, ValueError, original_error, None)
    assert "ValueError: original scrape failure" in diagnostics.files["before-cleanup-error.txt"]
    assert "diagnostic interrupted" in diagnostics.files["remote.capture-error.txt"]
    retained = diagnostics.directories["call"] / "before-cleanup-error.txt"
    assert "ValueError: original scrape failure" in retained.read_text()


def test_error_persistence_interrupt_still_runs_original_cleanup(
    retained_remote, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostics, session, original_exit, _ = retained_remote
    monkeypatch.setattr(diagnostics, "before_exit", MagicMock(side_effect=KeyboardInterrupt("capture interrupted")))
    RemoteSession.__exit__(session, None, None, None)
    original_exit.assert_called_once_with(session, None, None, None)
    session.client.page.request.assert_not_called()
    assert "capture interrupted" in diagnostics.files["remote.capture-error.txt"]


def test_diagnostic_transport_deadline_keeps_original_failure_and_cleanup(retained_remote) -> None:
    diagnostics, session, original_exit, _ = retained_remote
    original_error = ValueError("original scrape failure")

    def deadline(endpoint, *, timeout):
        assert timeout == flake_diagnostics._REMOTE_CAPTURE_TIMEOUT_SECONDS
        raise TimeoutError("diagnostic transport deadline expired")

    session.client.page.request.side_effect = deadline
    RemoteSession.__exit__(session, ValueError, original_error, None)
    session.client.page.request.assert_called_once()
    original_exit.assert_called_once_with(session, ValueError, original_error, None)
    assert session.client.root_client.max_retries == 3
    assert "ValueError: original scrape failure" in diagnostics.files["before-cleanup-error.txt"]
    assert "diagnostic transport deadline expired" in diagnostics.files["observation.txt.capture-error.txt"]


def test_original_session_interrupt_keeps_its_original_behavior(retained_remote) -> None:
    _, session, original_exit, _ = retained_remote
    original_error = KeyboardInterrupt("original test interrupt")
    original_exit.side_effect = original_error
    with pytest.raises(KeyboardInterrupt) as interrupted:
        RemoteSession.__exit__(session, KeyboardInterrupt, original_error, None)
    assert interrupted.value is original_error
    assert session.client.root_client.max_retries == 3
    original_exit.assert_called_once_with(session, KeyboardInterrupt, original_error, None)


def test_remote_capture_request_has_short_budget_and_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    with NotteClient(
        api_key="fixture-diagnostic-key",  # pragma: allowlist secret
        server_url=SERVER,
        max_retries=3,
    ) as client:
        transport = fake(monkeypatch, {"detail": "fixture observation unavailable"}, status_code=503)
        session = client.Session()
        session.response = SessionResponse.model_validate({**SESSION, "session_id": "fixture-session"})
        diagnostics = flake_diagnostics.Diagnostics()
        diagnostics.remote(session)
        assert len(transport.calls) == 1
        request = transport.calls[0]
        assert request.method == "POST"
        assert request.url == f"{SERVER}/sessions/fixture-session/page/observe"
        assert request.timeout
        assert all(
            timeout is not None and 0 < timeout <= flake_diagnostics._REMOTE_CAPTURE_TIMEOUT_SECONDS
            for timeout in request.timeout.values()
        )
        assert client.max_retries == 3
        assert "fixture observation unavailable" in diagnostics.files["observation.txt.capture-error.txt"]
