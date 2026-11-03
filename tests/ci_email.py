"""Sending for live persona email checks, through Resend's API."""

import os

import httpx
import pytest

RESEND_EMAILS_URL = "https://api.resend.com/emails"
RESEND_API_KEY_ENV = "PERSONA_TEST_RESEND_API_KEY"  # pragma: allowlist secret
SENDER_ENV = "PERSONA_TEST_EMAIL_FROM"
DEFAULT_SENDER = "Notte CI <persona-probe@tx.notte.cc>"
# Resend answers 429 with these names once the account's sending quota is used up.
RESEND_QUOTA_ERRORS = frozenset({"daily_quota_exceeded", "monthly_quota_exceeded"})


def require_email_configuration() -> None:
    if not os.getenv(RESEND_API_KEY_ENV):
        pytest.skip(f"{RESEND_API_KEY_ENV} required")


def send_test_email(recipient: str, subject: str) -> str:
    """Send one probe and return its sender. A used-up sending quota skips the test."""
    require_email_configuration()
    api_key = os.environ[RESEND_API_KEY_ENV]
    sender = os.getenv(SENDER_ENV) or DEFAULT_SENDER
    response = httpx.post(
        RESEND_EMAILS_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "text": f"Notte persona email delivery test: {subject}",
        },
        timeout=30,
    )
    if response.is_success:
        return sender
    try:
        error = response.json()
    except ValueError:
        error = None
    error_name = error.get("name") if isinstance(error, dict) else None
    if response.status_code == 429 and error_name in RESEND_QUOTA_ERRORS:
        pytest.skip(f"Resend sending quota exhausted ({error_name}); live email delivery cannot be checked.")
    raise AssertionError(f"Resend rejected the persona probe: HTTP {response.status_code} {response.text}")
