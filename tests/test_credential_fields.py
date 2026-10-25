import pyotp
import pytest
from notte_core.credentials.base import BaseVault, CredentialField, EmailField, totp_code


def test_dumping_a_credential_field_leaves_it_unchanged() -> None:
    field = EmailField(value="user@test.com")

    dumped = field.model_dump()
    assert dumped == {"value": "user@test.com", "field_name": "email"}

    # The frozen model must not gain the serialized-only key.
    assert field.__dict__ == {"value": "user@test.com"}
    assert not hasattr(field, "field_name")
    assert CredentialField.from_dict(field.model_dump()) == field


def test_non_string_credential_value_error_names_its_type() -> None:
    with pytest.raises(ValueError, match="Invalid credential type <class 'int'>, should be str"):
        _ = BaseVault.credentials_dict_to_field({"password": 123})  # pyright: ignore[reportArgumentType]


def test_totp_code_applies_otpauth_uri_settings() -> None:
    uri = "otpauth://totp/Example:me?secret=JBSWY3DPEHPK3PXP&digits=8&period=60&algorithm=SHA256"  # pragma: allowlist secret
    code = totp_code(uri)
    assert len(code) == 8
    assert pyotp.parse_uri(uri).verify(code, valid_window=1)
    assert pyotp.TOTP("JBSWY3DPEHPK3PXP").verify(
        totp_code("JBSWY3DPEHPK3PXP"), valid_window=1
    )  # pragma: allowlist secret


def test_totp_code_rejects_hotp_uris() -> None:
    with pytest.raises(ValueError, match="otpauth://totp"):
        _ = totp_code("otpauth://hotp/Example:me?secret=JBSWY3DPEHPK3PXP&counter=0")  # pragma: allowlist secret
