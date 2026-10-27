import pyotp
import pytest
from notte_core.credentials.base import BaseVault, CredentialField, EmailField, totp_code

from tests.mock.mock_vault import MockVault

TEST_PASSWORD = "test-password"  # pragma: allowlist secret


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


@pytest.mark.parametrize("issuer", ["AT%26T", "Example%3ATeam"])
def test_totp_uri_keeps_encoded_label_and_query_delimiters(issuer: str) -> None:
    uri = f"otpauth://totp/{issuer}:me?secret=JBSWY3DPEHPK3PXP&issuer={issuer}"
    assert pyotp.TOTP("JBSWY3DPEHPK3PXP").verify(totp_code(uri), valid_window=1)


@pytest.mark.asyncio
async def test_numeric_seeds_in_standard_vaults_still_generate_codes() -> None:
    seed = "23456723"
    vault = MockVault({"https://example.com": {"password": TEST_PASSWORD, "mfa_secret": seed}})
    creds = await vault.get_credentials_async("https://example.com")
    assert creds is not None and pyotp.TOTP(seed).verify(creds["mfa_secret"], valid_window=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("from_env", [False, True])
async def test_saving_a_totp_uri_accepts_the_same_formats_as_retrieval(
    monkeypatch: pytest.MonkeyPatch, from_env: bool
) -> None:
    uri = "otpauth://totp/AT%26T:me?secret=JBSWY3DPEHPK3PXP&issuer=AT%26T&digits=8&period=60&algorithm=SHA256"
    vault = MockVault()
    url = "https://example.com"
    if from_env:
        monkeypatch.setenv("EXAMPLE_COM_USERNAME", "me")
        monkeypatch.setenv("EXAMPLE_COM_PASSWORD", TEST_PASSWORD)
        monkeypatch.setenv("EXAMPLE_COM_MFA_SECRET", uri)
        await vault.add_credentials_from_env_async(url)
    else:
        await vault.add_credentials_async(url, username="me", password=TEST_PASSWORD, mfa_secret=uri)
    creds = await vault.get_credentials_async(url)
    assert creds is not None and creds["username"] == "me" and creds["password"] == TEST_PASSWORD
    assert len(creds["mfa_secret"]) == 8
    assert pyotp.parse_uri(uri).verify(creds["mfa_secret"], valid_window=1)
