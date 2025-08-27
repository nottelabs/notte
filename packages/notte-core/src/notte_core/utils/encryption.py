import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pydantic import BaseModel, SecretStr, field_validator


class Encryption(BaseModel):
    root_key: SecretStr | str

    @field_validator("root_key")
    def validate_root_key(cls, v: str) -> SecretStr:
        if not v:
            raise ValueError("Root key cannot be empty")
        if isinstance(v, SecretStr):
            return v
        return SecretStr(v)

    def _derive_key(self, salt: bytes | None = None) -> tuple[bytes, bytes]:
        """
        Derive a secure encryption key from the root key using PBKDF2.
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,  # High iteration count for security
        )
        root_key = self.root_key.get_secret_value() if isinstance(self.root_key, SecretStr) else self.root_key
        key = base64.urlsafe_b64encode(kdf.derive(root_key.encode()))
        return key, salt

    def encrypt(self, data: str) -> str:
        """
        Encrypt data using Fernet (AES-128-CBC with HMAC-SHA256).
        """
        key, salt = self._derive_key()
        f = Fernet(key)
        encrypted = f.encrypt(data.encode())

        # Combine salt + encrypted data for storage
        combined = salt + encrypted
        return base64.urlsafe_b64encode(combined).decode()

    def decrypt(self, token: str) -> str:
        """
        Decrypt data using Fernet.
        """
        combined = base64.urlsafe_b64decode(token.encode())

        # Extract salt and encrypted data
        salt = combined[:16]
        encrypted = combined[16:]

        key, _ = self._derive_key(salt)
        f = Fernet(key)
        decrypted = f.decrypt(encrypted)
        return decrypted.decode()
