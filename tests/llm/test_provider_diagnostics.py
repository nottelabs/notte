"""Offline evidence contracts for failed and interrupted provider requests."""

import asyncio
import json

import httpx
import pytest

from tests import flake_diagnostics
from tests.flake_diagnostics import Diagnostics
from tests.llm import test_provider_matrix as live_matrix
from tests.llm.provider_matrix import ROUTES, Attempt, Trace


def test_cached_completion_redacts_before_serialization_and_truncation(monkeypatch):
    key = 'selected-credential-"quoted"'
    monkeypatch.setenv("OPENROUTER_API_KEY", key)
    nested_value = "nested-sensitive-value"
    userinfo = ":".join(("fixture-user", "fixture-password"))
    nested = json.dumps({"api_key": nested_value})
    cutoff = json.dumps({"secret": "cutoff-sensitive-value" + "y" * 1_000})
    content = f"{key} {nested} https://{userinfo}@example.com/private?token=hidden " + "x" * 63_850 + cutoff
    attempt = Attempt("strict")
    Trace.response(
        attempt,
        httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "messages": [{"content": "request-prompt-must-not-be-retained"}],
                "headers": {"Authorization": "unrelated-header-must-not-be-retained"},
            },
        ),
        key,
    )
    assert len(attempt.completion) <= 64_000
    for sensitive in (
        "selected-credential",
        "nested-sensitive-value",
        "cutoff-sensitive-value",
        userinfo,
        "/private",
        "token=hidden",
        "request-prompt-must-not-be-retained",
        "unrelated-header-must-not-be-retained",
    ):
        assert sensitive not in attempt.completion
    assert "[REDACTED]" in attempt.completion


def test_observation_does_not_consume_uncached_response():
    class UnreadStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("Diagnostics must not read the response stream")
            yield b""

    attempt = Attempt("strict")
    response = httpx.Response(200, stream=UnreadStream())
    Trace.response(attempt, response, "test-key")
    assert attempt.status == 200
    assert not response.is_stream_consumed
    assert attempt.completion == "Response body was not cached"


@pytest.mark.asyncio
async def test_request_progress_survives_cancellation(monkeypatch, tmp_path, request):
    monkeypatch.setattr(flake_diagnostics, "ARTIFACT_PATH", tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "cancelled-test-key")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw4")
    cancellation = asyncio.CancelledError()

    async def send(client, http_request, **kwargs):
        progress = json.loads(next(tmp_path.rglob("provider-progress.json")).read_text())
        # This exists before the provider await completes or JUnit is finalized.
        assert progress["phase"] == "request_started"
        assert progress["route"] == "kimi"
        assert progress["case"] == "checkout/article"
        assert progress["worker"] == "gw4"
        assert progress["attempts"] == [{"format": "strict", "status": None}]
        raise cancellation

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    route = next(route for route in ROUTES if route.name == "kimi")
    with pytest.raises(asyncio.CancelledError) as raised:
        await live_matrix.test_provider_matrix(route, "checkout/article", monkeypatch, lambda *_: None, request)
    assert raised.value is cancellation
    progress = json.loads(next(tmp_path.rglob("provider-progress.json")).read_text())
    assert progress["phase"] == "request_interrupted"
    assert not list(tmp_path.rglob("provider-completions.txt"))
    assert "cancelled-test-key" not in json.dumps(progress)


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [False, True])
async def test_only_failed_extractions_publish_cached_completions(success, monkeypatch, tmp_path, request):
    monkeypatch.setattr(flake_diagnostics, "ARTIFACT_PATH", tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "completion-test-key")

    async def send(client, http_request, **kwargs):
        result = {"success": success, "error": None if success else "completion-test-key", "data": None}
        if success:
            result["data"] = {
                "title": "Title",
                "links": [
                    {"label": label, "url": f"link{index}"}
                    for index, (label, _) in enumerate(live_matrix.EXPECTED_LINKS["checkout/article"], 1)
                ],
            }
        return httpx.Response(
            200, request=http_request, json={"choices": [{"message": {"content": json.dumps(result)}}]}
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    route = next(route for route in ROUTES if route.name == "kimi")
    if success:
        await live_matrix.test_provider_matrix(route, "checkout/article", monkeypatch, lambda *_: None, request)
        assert not list(tmp_path.rglob("provider-completions.txt"))
    else:
        with pytest.raises(AssertionError):
            await live_matrix.test_provider_matrix(route, "checkout/article", monkeypatch, lambda *_: None, request)
        completion = next(tmp_path.rglob("provider-completions.txt")).read_text()
        assert "completion-test-key" not in completion
        assert "[REDACTED]" in completion
        assert "strict" in completion and "200" in completion
    progress = json.loads(next(tmp_path.rglob("provider-progress.json")).read_text())
    assert progress["phase"] == ("passed" if success else "failed")


@pytest.mark.asyncio
async def test_diagnostic_write_failure_preserves_provider_error(monkeypatch, tmp_path, request):
    monkeypatch.setattr(flake_diagnostics, "ARTIFACT_PATH", tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    provider_error = RuntimeError("original provider failure")
    original_write = Diagnostics.write

    def write(self, item, phase, files):
        if json.loads(files["provider-progress.json"])["phase"] in ("request_interrupted", "failed"):
            raise OSError("diagnostic storage unavailable")
        return original_write(self, item, phase, files)

    async def send(client, http_request, **kwargs):
        raise provider_error

    monkeypatch.setattr(Diagnostics, "write", write)
    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    route = next(route for route in ROUTES if route.name == "kimi")
    with pytest.raises(RuntimeError) as raised:
        await live_matrix.test_provider_matrix(route, "checkout/article", monkeypatch, lambda *_: None, request)
    assert raised.value is provider_error
    assert any("OSError" in note for note in provider_error.__notes__)
