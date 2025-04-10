from __future__ import annotations

import traceback
from typing import final

import tldextract
from loguru import logger
from typing_extensions import override

from notte.common.credential_vault.base import (
    BaseVault,
    CredentialField,
    VaultCredentials,
)
from notte.sdk.client import NotteClient


@final
class SdkVault(BaseVault):
    """Vault that fetches credentials stored using the sdk"""

    def __init__(self, sdk_client: NotteClient, persona_id: str):
        self.sdk_client = sdk_client
        self.persona_id = persona_id

    @staticmethod
    def get_root_domain(url: str) -> str:
        extracted = tldextract.extract(url)
        return ".".join((extracted.domain, extracted.suffix)) or url

    @override
    async def set_singleton_credentials(self, creds: list[CredentialField]) -> None:
        for cred in creds:
            if not cred.singleton:
                raise ValueError(f"{cred.__class__} can't be set as singleton credential: url-specific only")

        _ = self.sdk_client.persona.add_credentials(self.persona_id, url=None, credentials=list(creds))

    @override
    async def get_singleton_credentials(self) -> list[CredentialField]:
        try:
            return self.sdk_client.persona.get_credentials(self.persona_id, url=None).credentials
        except Exception as e:
            logger.warning(f"Could not get singleton credentials: {e} {traceback.format_exc()}")
            return []

    @override
    async def add_credentials(self, creds: VaultCredentials) -> None:
        for cred in creds.creds:
            if cred.singleton:
                raise ValueError(f"{cred.__class__} can't be set as url specific credential: singleton only")

        domain = SdkVault.get_root_domain(creds.url)
        _ = self.sdk_client.persona.add_credentials(self.persona_id, url=domain, credentials=list(creds.creds))

    @override
    async def _get_credentials_impl(self, url: str) -> VaultCredentials | None:
        try:
            domain = SdkVault.get_root_domain(url)
            creds = self.sdk_client.persona.get_credentials(self.persona_id, url=domain).credentials
            return VaultCredentials(url=url, creds=creds)
        except Exception:
            logger.warning(f"Failed to get creds: {traceback.format_exc()}")

    @override
    async def remove_credentials(self, url: str | None) -> None:
        _ = self.sdk_client.persona.delete_credentials(self.persona_id, url=url)
