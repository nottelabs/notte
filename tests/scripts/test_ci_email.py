import json

import httpx
import pytest

from tests import ci_email
from tests.ci_email import require_email_configuration, send_test_email

KEY = "re_test_key"  # pragma: allowlist secret


class FakeResend:
    """Answers Resend's API with queued responses and records each request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)


@pytest.fixture
def resend(monkeypatch: pytest.MonkeyPatch) -> FakeResend:
    monkeypatch.setenv(ci_email.RESEND_API_KEY_ENV, KEY)
    monkeypatch.delenv(ci_email.SENDER_ENV, raising=False)
    fake = FakeResend()

    def post(url: str, *, headers: dict[str, str], json: dict[str, str | list[str]], timeout: float) -> httpx.Response:
        with httpx.Client(transport=httpx.MockTransport(fake.handle)) as client:
            return client.post(url, headers=headers, json=json, timeout=timeout)

    monkeypatch.setattr(ci_email.httpx, "post", post)
    return fake


def test_send_posts_one_probe_and_returns_the_sender(resend: FakeResend) -> None:
    resend.responses.append(httpx.Response(200, json={"id": "email-1"}))

    assert send_test_email("persona@example.test", "delivery check") == ci_email.DEFAULT_SENDER

    [request] = resend.requests
    assert str(request.url) == ci_email.RESEND_EMAILS_URL
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert body["from"] == ci_email.DEFAULT_SENDER
    assert body["to"] == ["persona@example.test"]
    assert body["subject"] == "delivery check"
    assert "delivery check" in body["text"]


def test_sender_can_be_overridden(resend: FakeResend, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ci_email.SENDER_ENV, "Other <probe@example.test>")
    resend.responses.append(httpx.Response(200, json={"id": "email-1"}))

    assert send_test_email("persona@example.test", "delivery check") == "Other <probe@example.test>"
    assert json.loads(resend.requests[0].content)["from"] == "Other <probe@example.test>"


@pytest.mark.parametrize("name", sorted(ci_email.RESEND_QUOTA_ERRORS))
def test_used_up_quota_skips(resend: FakeResend, name: str) -> None:
    resend.responses.append(httpx.Response(429, json={"name": name, "message": "quota"}))

    with pytest.raises(pytest.skip.Exception, match="quota exhausted"):
        _ = send_test_email("persona@example.test", "delivery check")


@pytest.mark.parametrize("name", sorted(ci_email.RESEND_QUOTA_ERRORS))
def test_used_up_quota_fails_a_rerun(resend: FakeResend, name: str) -> None:
    resend.responses.append(httpx.Response(429, json={"name": name, "message": "quota"}))

    with pytest.raises(AssertionError, match="on a rerun"):
        _ = send_test_email("persona@example.test", "delivery check", first_attempt=False)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"name": "rate_limit_exceeded"}),
        httpx.Response(403, json={"name": "validation_error", "message": "domain not verified"}),
        httpx.Response(401, json={"name": "missing_api_key"}),
        httpx.Response(500, text="not json"),
    ],
)
def test_other_rejections_fail(resend: FakeResend, response: httpx.Response) -> None:
    resend.responses.append(response)

    with pytest.raises(AssertionError, match=f"HTTP {response.status_code}"):
        _ = send_test_email("persona@example.test", "delivery check")


def test_missing_key_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ci_email.RESEND_API_KEY_ENV, raising=False)

    with pytest.raises(pytest.skip.Exception, match=ci_email.RESEND_API_KEY_ENV):
        require_email_configuration()
