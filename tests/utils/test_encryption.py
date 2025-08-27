import pytest
from notte_core.utils.encryption import Encryption


@pytest.fixture
def encryption() -> Encryption:
    return Encryption(root_key="test_secret_key_123")


def test_encrypt_decrypt_basic(encryption: Encryption):
    """Test basic encryption and decryption functionality."""
    original = "Hello, World!"
    encrypted = encryption.encrypt(original)
    decrypted = encryption.decrypt(encrypted)
    assert decrypted == original


def test_encrypt_decrypt_empty_string(encryption: Encryption):
    """Test encryption and decryption of empty string."""
    original = ""
    encrypted = encryption.encrypt(original)
    decrypted = encryption.decrypt(encrypted)
    assert decrypted == original


def test_encrypt_decrypt_unicode(encryption: Encryption):
    """Test encryption and decryption of unicode characters."""
    original = "Hello 世界! 🌍"
    encrypted = encryption.encrypt(original)
    decrypted = encryption.decrypt(encrypted)
    assert decrypted == original


def test_encrypt_decrypt_long_text(encryption: Encryption):
    """Test encryption and decryption of long text."""
    original = "A" * 1000
    encrypted = encryption.encrypt(original)
    decrypted = encryption.decrypt(encrypted)
    assert decrypted == original


def test_encrypt_produces_different_outputs(encryption: Encryption):
    """Test that encryption produces different outputs for same input due to salt."""
    original = "test"
    encrypted1 = encryption.encrypt(original)
    encrypted2 = encryption.encrypt(original)
    assert encrypted1 != encrypted2


def test_decrypt_with_different_key_fails(encryption: Encryption):
    """Test that decryption fails with wrong key."""
    enc1 = Encryption(root_key="key1")
    enc2 = Encryption(root_key="key2")

    original = "test"
    encrypted = enc1.encrypt(original)

    with pytest.raises(Exception):  # Should raise cryptography.fernet.InvalidToken
        _ = enc2.decrypt(encrypted)


def test_decrypt_invalid_token(encryption: Encryption):
    """Test that decryption fails with invalid token."""
    with pytest.raises(Exception):  # Should raise base64 or cryptography error
        _ = encryption.decrypt("invalid_token")


def test_encryption_model_validation(encryption: Encryption):
    """Test that Encryption model validates correctly."""
    # Should work with valid key
    encryption = Encryption(root_key="valid_key")
    assert encryption.root_key.get_secret_value() == "valid_key"

    # Should work with empty key (though not recommended)
    with pytest.raises(ValueError):
        _ = Encryption(root_key="")


def test_encrypt_decrypt_special_characters(encryption: Encryption):
    """Test encryption and decryption of special characters."""
    original = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
    encrypted = encryption.encrypt(original)
    decrypted = encryption.decrypt(encrypted)
    assert decrypted == original


def test_encrypt_decrypt_multiline(encryption: Encryption):
    """Test encryption and decryption of multiline text."""
    original = "Line 1\nLine 2\nLine 3"
    encrypted = encryption.encrypt(original)
    decrypted = encryption.decrypt(encrypted)
    assert decrypted == original


def test_encrypt_decrypt_json_like(encryption: Encryption):
    """Test encryption and decryption of JSON-like data."""
    original = '{"key": "value", "number": 123, "array": [1, 2, 3]}'
    encrypted = encryption.encrypt(original)
    decrypted = encryption.decrypt(encrypted)
    assert decrypted == original
