from notte_core.credentials.base import BaseVault, Credential, CredentialsDict, CreditCardDict


class MockVault(BaseVault):
    """A minimal vault implementation for testing without API calls."""

    def __init__(self, creds_by_url: dict[str, CredentialsDict] | None = None):
        super().__init__()
        self._creds_by_url: dict[str, CredentialsDict] = creds_by_url or {}
        self._card: CreditCardDict | None = None

    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        self._creds_by_url[url] = creds

    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        return self._creds_by_url.get(url)

    async def delete_credentials_async(self, url: str) -> None:
        self._creds_by_url.pop(url, None)

    async def set_credit_card_async(self, **kwargs: CreditCardDict) -> None:
        self._card = kwargs

    async def get_credit_card_async(self) -> CreditCardDict:
        if self._card is None:
            return {
                "card_holder_name": "John Doe",
                "card_number": "4242 4242 4242 4242",
                "card_cvv": "123",
                "card_full_expiration": "12/30",
            }
        return self._card

    async def list_credentials_async(self) -> list[Credential]:
        return [
            Credential(url=url, email=creds.get("email"), username=creds.get("username"))
            for url, creds in self._creds_by_url.items()
        ]

    async def delete_credit_card_async(self) -> None:
        self._card = None
