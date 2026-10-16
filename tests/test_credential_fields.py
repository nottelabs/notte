import pytest
from notte_core.credentials.base import BaseVault, CredentialField, EmailField


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
