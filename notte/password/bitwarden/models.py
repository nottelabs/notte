from typing import Dict, Optional
import requests
from loguru import logger
from notte.password.vault import Vault
from notte.password.models import Credentials

class BitwardenVault(Vault):
    def __new__(cls, server_url: str, api_key: str) -> "BitwardenVault":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, server_url: str, api_key: str):
        if self._initialized:
            return
        
        super().__init__()  # Call parent's __init__ with no vault_path
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })
        self._initialized = True

    def _get_bitwarden_items(self) -> list:
        print(self.server_url)
        response = self.session.get(f"{self.server_url}/api/sync")
        print(response.json())
        if response.status_code != 200:
            raise ValueError(f"Failed to fetch items from Bitwarden: {response.text}")
        return response.json().get('items', [])

    def sync_with_bitwarden(self) -> None:
        """Sync credentials from Bitwarden to local vault"""
        items = self._get_bitwarden_items()
        print(items)
        
        for item in items:
            if item.get('type') == 1:  # Login type
                login = item.get('login', {})
                uri = login.get('uri', '')
                if uri:
                    creds = Credentials(
                        url=uri,
                        username=login.get('username', ''),
                        password=login.get('password', '')
                    )
                    self.add_credentials(
                        url=uri,
                        username=creds.username,
                        password=creds.password
                    )
        
        logger.info(f"Synced {len(items)} items from Bitwarden")
