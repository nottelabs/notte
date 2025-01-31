import json
import os
from pathlib import Path
from typing import ClassVar, Dict, Optional
from urllib.parse import urlparse

import keyring
from cryptography.fernet import Fernet
from loguru import logger

from notte.utils.url import clean_url

from .models import Credentials


class Vault:
    _instance: ClassVar[Optional["Vault"]] = None

    def __new__(cls, vault_path: Optional[str] = None) -> "Vault":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, vault_path: Optional[str] = None):
        if self._initialized:
            return

        self._vault_path = Path(vault_path or os.path.expanduser("~/.notte/vault.json"))
        self._vault_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize encryption key
        self._key_id = "notte-vault-key"
        self._init_encryption()

        # Load existing credentials
        self._credentials: Dict[str, Credentials] = {}
        self._load_vault()
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "Vault":
        if cls._instance is None:
            cls._instance = Vault()
        return cls._instance

    def _init_encryption(self) -> None:
        key = keyring.get_password("notte", self._key_id)
        if not key:
            key = Fernet.generate_key().decode()
            keyring.set_password("notte", self._key_id, key)
        self._fernet = Fernet(key.encode())

    def _load_vault(self) -> None:
        if not self._vault_path.exists():
            return

        try:
            with open(self._vault_path, "r") as f:
                encrypted_data = json.load(f)

            for domain, encrypted_creds in encrypted_data.items():
                decrypted = self._fernet.decrypt(encrypted_creds.encode()).decode()
                creds_dict = json.loads(decrypted)
                self._credentials[domain] = Credentials(**creds_dict)

        except Exception as e:
            logger.error(f"Failed to load vault: {e}")
            raise ValueError(f"Failed to load vault file: {e}")

    def _save_vault(self) -> None:
        encrypted_data = {}

        for domain, creds in self._credentials.items():
            creds_dict = {"url": creds.url, "username": creds.username, "password": creds.password}
            encrypted = self._fernet.encrypt(json.dumps(creds_dict).encode()).decode()
            encrypted_data[domain] = encrypted

        with open(self._vault_path, "w") as f:
            json.dump(encrypted_data, f, indent=4)

    def add_vault(self, vault: Dict[str, Dict[str, str]]) -> None:
        """Add credentials from a vault dictionary

        Expected format:
        {
            "domain.com": {
                "username": "user",
                "password": "pass"
            }
        }
        """
        for domain, creds_dict in vault.items():
            # Create Credentials object with the domain as URL
            creds = Credentials(
                url=f"https://{domain}", username=creds_dict["username"], password=creds_dict["password"]
            )
            self._credentials[domain] = creds
        self._save_vault()
        logger.info(f"Added vault with {len(vault)} credentials")

    def add_credentials(self, url: str, username: str, password: str) -> None:
        domain = clean_url(url)
        self._credentials[domain] = Credentials(url=url, username=username, password=password)
        self._save_vault()
        logger.info(f"Added credentials for {domain}")

    def get_credentials(self, url: str) -> Optional[Credentials]:
        domain = clean_url(url)
        return self._credentials.get(domain)

    def remove_credentials(self, url: str) -> None:
        domain = clean_url(url)
        if domain in self._credentials:
            del self._credentials[domain]
            self._save_vault()
            logger.info(f"Removed credentials for {domain}")

    def list_domains(self) -> list[str]:
        return list(self._credentials.keys())
