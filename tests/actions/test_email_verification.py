import pytest
from notte_core.actions import ActionUnion, EmailVerificationReadAction
from pydantic import TypeAdapter, ValidationError


def test_email_verification_read_action_round_trip() -> None:
    action = EmailVerificationReadAction(sender_domain="auth.example.com", max_age_seconds=600)

    parsed = TypeAdapter(ActionUnion).validate_python(action.model_dump())

    assert parsed == action
    assert parsed.type == "email_verification_read"


@pytest.mark.parametrize(
    ("sender_domain", "max_age_seconds"),
    [
        ("", 300),
        ("example.com", 29),
        ("example.com", 901),
    ],
)
def test_email_verification_read_action_rejects_invalid_fields(sender_domain: str, max_age_seconds: int) -> None:
    with pytest.raises(ValidationError):
        EmailVerificationReadAction(sender_domain=sender_domain, max_age_seconds=max_age_seconds)
