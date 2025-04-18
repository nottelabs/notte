from __future__ import annotations

import traceback
from typing import final

import tldextract
from loguru import logger
from notte_core.credentials.base import (
    BaseVault,
    CredentialField,
    VaultCredentials,
)
from typing_extensions import override

from notte_sdk.endpoints.persona import PersonaClient


@final
class NotteVault(BaseVault):
    """Vault that fetches credentials stored using the sdk"""

    def __init__(self, persona_client: PersonaClient, persona_id: str):
        self.persona_client = persona_client
        self.persona_id = persona_id

    @property
    def vault_id(self):
        return self.persona_id

    @staticmethod
    def get_root_domain(url: str) -> str:
        extracted = tldextract.extract(url)
        return ".".join((extracted.domain, extracted.suffix)) or url

    @override
    async def _set_singleton_credentials(self, creds: list[CredentialField]) -> None:
        for cred in creds:
            if not cred.singleton:
                raise ValueError(f"{cred.__class__} can't be set as singleton credential: url-specific only")

        creds_dict = BaseVault.credential_fields_to_dict(creds)
        _ = self.persona_client.add_credentials(self.persona_id, url=None, **creds_dict)

    @override
    async def get_singleton_credentials(self) -> list[CredentialField]:
        try:
            return self.persona_client.get_credentials(self.persona_id, url=None).credentials
        except Exception as e:
            logger.warning(f"Could not get singleton credentials: {e} {traceback.format_exc()}")
            return []

    @override
    async def _add_credentials(self, creds: VaultCredentials) -> None:
        for cred in creds.creds:
            if cred.singleton:
                raise ValueError(f"{cred.__class__} can't be set as url specific credential: singleton only")

        domain = NotteVault.get_root_domain(creds.url)
        creds_dict = BaseVault.credential_fields_to_dict(creds.creds)
        _ = self.persona_client.add_credentials(self.persona_id, url=domain, **creds_dict)

    @override
    async def _get_credentials_impl(self, url: str) -> VaultCredentials | None:
        try:
            domain = NotteVault.get_root_domain(url)
            creds = self.persona_client.get_credentials(self.persona_id, url=domain).credentials
            return VaultCredentials(url=url, creds=creds)
        except Exception:
            logger.warning(f"Failed to get creds: {traceback.format_exc()}")

    @override
    async def remove_credentials(self, url: str | None) -> None:
        _ = self.persona_client.delete_credentials(self.persona_id, url=url)
