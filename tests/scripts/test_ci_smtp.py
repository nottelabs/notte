import smtplib
from unittest.mock import MagicMock

import pytest

from tests.ci_smtp import require_smtp_configuration, send_test_email, sender_quota_exhausted

QUOTA = b"5.4.6 Sender Daily Quota Exceeded"


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("SMTP_SERVER", "smtp.example.test")
    monkeypatch.setenv("EMAIL_SENDER", "sender@example.test")
    monkeypatch.setenv("EMAIL_PASSWORD", "test")  # pragma: allowlist secret
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_STARTTLS", raising=False)
    transport = MagicMock()
    transport.__enter__.return_value = transport
    transport.__exit__.return_value = False
    monkeypatch.setattr(smtplib, "SMTP", MagicMock(return_value=transport))
    monkeypatch.setattr(smtplib, "SMTP_SSL", MagicMock(return_value=transport))
    return transport


@pytest.mark.parametrize("port", [587, 465])
def test_send_succeeds_and_closes_transport(smtp: MagicMock, monkeypatch: pytest.MonkeyPatch, port: int) -> None:
    monkeypatch.setenv("SMTP_PORT", str(port))
    assert send_test_email("persona@example.test", "delivery check") == "sender@example.test"
    smtp.login.assert_called_once_with("sender@example.test", "test")
    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "persona@example.test"
    assert message["Subject"] == "delivery check"
    assert "delivery check" in message.get_content()
    assert smtp.starttls.call_count == (0 if port == 465 else 1)
    smtp.__exit__.assert_called_once()


def test_starttls_can_be_disabled(smtp: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    _ = send_test_email("persona@example.test", "delivery check")
    smtp.starttls.assert_not_called()


@pytest.mark.parametrize("port", [587, 465])
@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPRecipientsRefused({"persona@example.test": (550, QUOTA)}),
        smtplib.SMTPRecipientsRefused({"persona@example.test": (550, QUOTA.decode())}),
        smtplib.SMTPDataError(550, QUOTA),
        smtplib.SMTPSenderRefused(550, QUOTA, "sender@example.test"),
    ],
)
def test_explicit_quota_skips_and_closes_transport(
    smtp: MagicMock, monkeypatch: pytest.MonkeyPatch, port: int, error: smtplib.SMTPException
) -> None:
    monkeypatch.setenv("SMTP_PORT", str(port))
    smtp.send_message.side_effect = error
    with pytest.raises(pytest.skip.Exception, match="daily quota exhausted"):
        _ = send_test_email("persona@example.test", "delivery check")
    assert sender_quota_exhausted(error)
    assert smtp.send_message.call_count == 1
    smtp.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPRecipientsRefused({"persona@example.test": (550, b"Mailbox unavailable")}),
        smtplib.SMTPRecipientsRefused(
            {"persona@example.test": (550, QUOTA), "other@example.test": (550, b"Mailbox unavailable")}
        ),
        smtplib.SMTPRecipientsRefused({}),
        smtplib.SMTPDataError(550, b"Message rejected"),
        smtplib.SMTPDataError(451, QUOTA),
        smtplib.SMTPAuthenticationError(535, b"Invalid credentials"),
        smtplib.SMTPServerDisconnected("Connection lost"),
    ],
)
def test_other_smtp_errors_still_fail(smtp: MagicMock, error: smtplib.SMTPException) -> None:
    smtp.send_message.side_effect = error
    with pytest.raises(type(error)) as caught:
        _ = send_test_email("persona@example.test", "delivery check")
    assert caught.value is error
    assert not sender_quota_exhausted(error)
    smtp.__exit__.assert_called_once()


def test_authentication_errors_still_fail(smtp: MagicMock) -> None:
    error = smtplib.SMTPAuthenticationError(535, b"Invalid credentials")
    smtp.login.side_effect = error
    with pytest.raises(smtplib.SMTPAuthenticationError):
        _ = send_test_email("persona@example.test", "delivery check")
    smtp.send_message.assert_not_called()


def test_missing_configuration_skips_before_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SMTP_SERVER", raising=False)
    monkeypatch.delenv("EMAIL_SENDER", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
    with pytest.raises(pytest.skip.Exception, match="SMTP_SERVER.*required"):
        require_smtp_configuration()
