from __future__ import annotations

from typing import Unpack, final

from notte_core.credentials.base import (
    BaseVault,
    CredentialsDict,
    CreditCardDict,
)
from typing_extensions import override

from notte_sdk.endpoints.vaults import VaultsClient


@final
class NotteVault(BaseVault):
    """Vault that fetches credentials stored using the sdk"""

    def __init__(self, vault_id: str, vault_client: VaultsClient | None = None):
        from notte_sdk.endpoints.vaults import VaultsClient

        self.vault_id: str = vault_id

        if vault_client is None:
            vault_client = VaultsClient()

        self.vault_client = vault_client

    @override
    def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        _ = self.vault_client.add_or_update_credentials(self.vault_id, url=url, **creds)

    @override
    def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        return self.vault_client.get_credentials(vault_id=self.vault_id, url=url).credentials

    @override
    def delete_credentials(self, url: str) -> None:
        _ = self.vault_client.delete_credentials(vault_id=self.vault_id, url=url)

    @override
    def set_credit_card(self, **kwargs: Unpack[CreditCardDict]) -> None:
        _ = self.vault_client.set_credit_card(self.vault_id, **kwargs)

    @override
    def get_credit_card(self) -> CreditCardDict:
        return self.vault_client.get_credit_card(self.vault_id).credit_card

    @override
    def delete_credit_card(self) -> None:
        _ = self.vault_client.delete_credit_card(self.vault_id)
