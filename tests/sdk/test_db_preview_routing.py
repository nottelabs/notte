"""NOTTE_DB_PREVIEW selects a database branch for a client's requests."""

import pytest
from notte_sdk.endpoints.base import BaseClient


class MockNotteClient:
    pass


def _client(api_key: str = "test-api-key") -> BaseClient:
    return BaseClient(MockNotteClient(), None, api_key=api_key)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTTE_DB_PREVIEW", raising=False)


def test_no_preview_header_by_default() -> None:
    assert "x-db-preview" not in _client().headers()


def test_preview_branch_is_sent_as_a_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_DB_PREVIEW", "feature/my-branch")
    assert _client().headers()["x-db-preview"] == "feature/my-branch"


def test_blank_values_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_DB_PREVIEW", "   ")
    assert "x-db-preview" not in _client().headers()


def test_branch_is_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_DB_PREVIEW", "  feature/my-branch  ")
    assert _client().headers()["x-db-preview"] == "feature/my-branch"


def test_explicit_headers_still_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_DB_PREVIEW", "feature/my-branch")
    headers = _client().headers({"x-db-preview": "explicit"})
    assert headers["x-db-preview"] == "explicit"


def test_websocket_url_is_unchanged_without_a_branch() -> None:
    url = "wss://api.notte.cc/agents/a/debug/logs?token=t"
    assert _client()._with_db_preview(url) == url


def test_websocket_url_carries_the_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_DB_PREVIEW", "feature/my-branch")
    url = "wss://api.notte.cc/agents/a/debug/logs?token=t"
    assert (
        _client()._with_db_preview(url)
        == "wss://api.notte.cc/agents/a/debug/logs?token=t&db_preview=feature%2Fmy-branch"
    )


def test_websocket_url_without_a_query_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_DB_PREVIEW", "main")
    assert _client()._with_db_preview("wss://api.notte.cc/ws") == "wss://api.notte.cc/ws?db_preview=main"


def test_branch_survives_a_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """The server parses this back out, so the encoding has to be recoverable."""
    from urllib.parse import parse_qsl, urlparse

    monkeypatch.setenv("NOTTE_DB_PREVIEW", "feature/a+b c")
    url = _client()._with_db_preview("wss://api.notte.cc/ws?token=t")
    assert dict(parse_qsl(urlparse(url).query))["db_preview"] == "feature/a+b c"
