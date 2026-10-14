"""SMTP prerequisites and sending for live email checks."""

import os
import smtplib
from email.message import EmailMessage

import pytest

SMTP_SERVER_ENV = "SMTP_SERVER"
SMTP_PORT_ENV = "SMTP_PORT"
SMTP_USERNAME_ENV = "EMAIL_SENDER"
SMTP_PASSWORD_ENV = "EMAIL_PASSWORD"  # pragma: allowlist secret
SMTP_STARTTLS_ENV = "SMTP_STARTTLS"


def require_smtp_configuration() -> None:
    missing = [name for name in (SMTP_SERVER_ENV, SMTP_USERNAME_ENV, SMTP_PASSWORD_ENV) if os.getenv(name) is None]
    if missing:
        pytest.skip(f"{', '.join(missing)} required")


def sender_quota_exhausted(error: smtplib.SMTPException) -> bool:
    """Recognize only explicit daily sender quota rejection, not other 550 errors."""
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        responses = list(error.recipients.values())
    elif isinstance(error, (smtplib.SMTPDataError, smtplib.SMTPSenderRefused)):
        responses = [(error.smtp_code, error.smtp_error)]
    else:
        return False
    return bool(responses) and all(
        code == 550
        and "sender daily quota exceeded"
        in (message.decode(errors="replace") if isinstance(message, bytes) else message).lower()
        for code, message in responses
    )


def send_test_email(recipient: str, subject: str) -> str:
    require_smtp_configuration()
    server = os.getenv(SMTP_SERVER_ENV)
    username = os.getenv(SMTP_USERNAME_ENV)
    password = os.getenv(SMTP_PASSWORD_ENV)
    assert server is not None
    assert username is not None
    assert password is not None

    host, _, server_port = server.partition(":")
    port = int(os.getenv(SMTP_PORT_ENV, server_port or "587"))
    message = EmailMessage()
    message["From"] = username
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(f"Notte persona email delivery test: {subject}")

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as connection:
                connection.login(username, password)
                connection.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=30) as connection:
                if os.getenv(SMTP_STARTTLS_ENV, "true").lower() != "false":
                    connection.starttls()
                connection.login(username, password)
                connection.send_message(message)
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError, smtplib.SMTPSenderRefused) as error:
        if sender_quota_exhausted(error):
            pytest.skip("SMTP sender daily quota exhausted; live email delivery cannot be checked.")
        raise
    return username
