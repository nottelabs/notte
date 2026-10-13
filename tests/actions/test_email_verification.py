import pytest
from notte_core.actions import ActionUnion, EmailVerificationReadAction
from pydantic import TypeAdapter, ValidationError


def test_email_verification_read_action_round_trip() -> None:
    action = EmailVerificationReadAction(mailbox_id="mbx_123", sender_domain="auth.example.com", max_age_seconds=600)

    parsed = TypeAdapter(ActionUnion).validate_python(action.model_dump())

    assert parsed == action
    assert parsed.type == "email_verification_read"
    assert parsed.mailbox_id == "mbx_123"


@pytest.mark.parametrize(
    ("mailbox_id", "sender_domain", "max_age_seconds"),
    [
        ("", "example.com", 300),
        ("mbx_123", "", 300),
        ("mbx_123", "example.com", 29),
        ("mbx_123", "example.com", 901),
    ],
)
def test_email_verification_read_action_rejects_invalid_fields(
    mailbox_id: str, sender_domain: str, max_age_seconds: int
) -> None:
    with pytest.raises(ValidationError):
        EmailVerificationReadAction(mailbox_id=mailbox_id, sender_domain=sender_domain, max_age_seconds=max_age_seconds)


def test_email_verification_read_action_requires_mailbox_id() -> None:
    with pytest.raises(ValidationError):
        EmailVerificationReadAction(sender_domain="example.com")  # pyright: ignore [reportCallIssue]
