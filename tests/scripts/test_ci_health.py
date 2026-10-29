"""Dependency errors stay visible and never print provider responses or keys."""

import io
import json
import signal
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler

import pytest

from scripts import ci_health


@pytest.mark.parametrize("code,payload", [(302, None), (303, {"messages": []})])
def test_redirects_do_not_forward_bearer_keys(monkeypatch: pytest.MonkeyPatch, code: int, payload) -> None:
    def respond(request, **kwargs):
        assert request.get_header("Authorization") == "Bearer fixture-private-key"
        redirected = HTTPRedirectHandler().redirect_request(
            request, None, code, "redirect", {}, "https://redirect.invalid/"
        )
        assert redirected is not None
        assert redirected.get_header("Authorization") is None
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(ci_health, "urlopen", respond)
    assert ci_health.read("https://fixture.invalid/", "fixture-private-key", payload) == {"ok": True}


@pytest.mark.parametrize(
    "code,status",
    [(401, "authentication"), (403, "authorization"), (402, "credits"), (429, "capacity"), (503, "service_error")],
)
def test_http_failure_is_classified_without_retry_or_secret(
    monkeypatch: pytest.MonkeyPatch, code: int, status: str
) -> None:
    calls = []

    def fail(request, **kwargs):
        calls.append(request)
        raise HTTPError(request.full_url, code, "private-provider-body", {}, None)

    monkeypatch.setattr(ci_health, "urlopen", fail)
    result = ci_health.probe("openrouter", "fixture-private-key")
    assert result["status"] == status
    assert result["http_status"] == code
    assert len(calls) == 1
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize(
    "error", [TimeoutError("private"), URLError("private"), ValueError("private"), IncompleteRead(b"private", 100)]
)
def test_transport_and_malformed_responses_fail(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(ci_health, "urlopen", fail)
    assert ci_health.probe("staging", "fixture-private-key")["status"] != "passed"


def test_no_credentials_never_makes_an_anonymous_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ci_health, "urlopen", lambda *args, **kwargs: pytest.fail("Network must not run"))
    assert ci_health.probe("openrouter", "")["status"] == "missing_credentials"


def test_staging_health_requires_the_usage_read_to_succeed(monkeypatch: pytest.MonkeyPatch) -> None:
    urls = []

    def respond(request, **kwargs):
        urls.append(request.full_url)
        assert kwargs == {"timeout": 10}
        assert request.get_header("User-agent") == "notte-ci-health/1.0"
        assert request.get_header("Authorization") == (
            None if request.full_url.endswith("/health") else "Bearer fixture-private-key"
        )
        payload = {"version": "fixture-version"} if request.full_url.endswith("/health") else {"items": []}
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(ci_health, "urlopen", respond)
    result = ci_health.probe("staging", "fixture-private-key")
    assert result["status"] == "passed"
    assert result["version"] == "fixture-version"
    assert len(urls) == 2 and "/usage/logs?" in urls[1]


@pytest.mark.parametrize(
    "payload,passed",
    [({"choices": [{"message": {"content": "OK"}}]}, True), ({"error": "private"}, False), ({"choices": []}, False)],
)
def test_provider_success_requires_a_completion(monkeypatch: pytest.MonkeyPatch, payload, passed: bool) -> None:
    def respond(request, **kwargs):
        assert request.full_url == "https://openrouter.ai/api/v1/chat/completions"
        assert json.loads(request.data)["provider"] == {"allow_fallbacks": False}
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(ci_health, "urlopen", respond)
    assert (ci_health.probe("openrouter", "fixture-private-key")["status"] == "passed") == passed


def test_body_deadline_restores_the_previous_signal_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    previous = signal.getsignal(signal.SIGALRM)

    class Heartbeat(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            signal.raise_signal(signal.SIGALRM)
            raise AssertionError("The body must be interrupted")

    monkeypatch.setattr(ci_health, "urlopen", lambda *args, **kwargs: Heartbeat())
    assert ci_health.probe("openrouter", "fixture-private-key")["status"] == "transport"
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


@pytest.mark.parametrize("code,status", [(402, "credits"), (429, "capacity"), (503, "service_error")])
def test_embedded_errors_preserve_transport_and_provider_status(
    monkeypatch: pytest.MonkeyPatch, code: int, status: str
) -> None:
    monkeypatch.setattr(
        ci_health,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(
            json.dumps({"error": {"code": code, "message": "private-provider-body"}}).encode()
        ),
    )
    result = ci_health.probe("openrouter", "fixture-private-key")
    assert result["status"] == status
    assert result["http_status"] == 200
    assert result["provider_status"] == code
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("status", ["passed", "transport"])
def test_cli_saves_evidence_and_fails_the_check_when_unhealthy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["ci_health", "openrouter"])
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    result: ci_health.Result = {
        "service": "openrouter",
        "status": status,
        "http_status": None,
        "provider_status": None,
        "elapsed_seconds": 1,
        "version": None,
    }
    monkeypatch.setattr(ci_health, "probe", lambda *args: result)
    if status == "passed":
        ci_health.main()
    else:
        with pytest.raises(SystemExit) as error:
            ci_health.main()
        assert error.value.code == 1
    assert json.loads((tmp_path / ".test-artifacts/ci-health/openrouter.json").read_text()) == result
    assert status in summary.read_text()
