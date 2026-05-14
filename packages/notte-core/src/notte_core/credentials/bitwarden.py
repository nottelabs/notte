from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING, Any, Unpack

from typing_extensions import override

from notte_core.common.logging import logger
from notte_core.common.resource import SyncResource
from notte_core.credentials.base import BaseVault, Credential, CredentialsDict, CreditCardDict
from notte_core.utils.url import get_root_domain

if TYPE_CHECKING:
    from bitwarden_sdk import BitwardenClient  # pyright: ignore[reportMissingTypeStubs]


def _get_sdk() -> tuple[Any, Any, Any]:
    """Import and return (BitwardenClient, DeviceType, client_settings_from_dict)."""
    try:
        from bitwarden_sdk import BitwardenClient as Cls  # pyright: ignore[reportMissingTypeStubs]
        from bitwarden_sdk import DeviceType as DT  # pyright: ignore[reportMissingTypeStubs]
        from bitwarden_sdk import client_settings_from_dict as csfd  # pyright: ignore[reportMissingTypeStubs]

        return Cls, DT, csfd
    except ImportError:
        raise ImportError(
            "bitwarden-sdk is required for BitwardenVault. Install it with: pip install bitwarden-sdk"
        ) from None


class BitwardenVault(BaseVault, SyncResource):
    """Vault backed by Bitwarden Secrets Manager via the official Python SDK.

    Requires: pip install bitwarden-sdk

    Credentials are fetched from a Bitwarden Secrets Manager project.
    Each secret's value must be a JSON object with the notte credential format:
    {"url": "https://...", "password": "...", "username": "...", "email": "...", "mfa_secret": "..."}

    Only `url` and `password` are required.
    """

    def __init__(
        self,
        access_token: str | None = None,
        organization_id: str | None = None,
        project_id: str | None = None,
        api_url: str = "https://api.bitwarden.com",
        identity_url: str = "https://identity.bitwarden.com",
    ):
        super().__init__()
        self._access_token: str = access_token or os.environ.get("BWS_ACCESS_TOKEN", "")
        self._organization_id: str | None = organization_id or os.environ.get("BWS_ORGANIZATION_ID")
        self._project_id: str | None = project_id
        self._api_url: str = api_url
        self._identity_url: str = identity_url
        self._client: BitwardenClient | None = None
        self._secrets_cache: list[Any] | None = None

    @override
    def start(self) -> None:
        if not self._access_token:
            raise ValueError("Bitwarden access token required. Set BWS_ACCESS_TOKEN env var or pass access_token=")

        bw_client_cls, device_type, settings_fn = _get_sdk()
        client: BitwardenClient = bw_client_cls(
            settings_fn(
                {
                    "apiUrl": self._api_url,
                    "deviceType": device_type.SDK,
                    "identityUrl": self._identity_url,
                    "userAgent": "notte",
                }
            )
        )
        _ = client.auth().login_access_token(self._access_token)
        self._client = client
        self._secrets_cache = self._fetch_secrets()
        logger.info(f"[BitwardenVault] Loaded {len(self._secrets_cache)} secrets")

    @override
    def stop(self) -> None:
        self._client = None
        self._secrets_cache = None

    def _fetch_secrets(self) -> list[Any]:
        assert self._client is not None
        if not self._organization_id:
            raise ValueError(
                "organization_id required to list secrets. Set BWS_ORGANIZATION_ID or pass organization_id="
            )

        response = self._client.secrets().list(self._organization_id)
        if response.data is None:
            return []

        secret_ids = [s.id for s in response.data.data]
        if not secret_ids:
            return []

        full_secrets = self._client.secrets().get_by_ids(secret_ids)
        if full_secrets.data is None:
            return []

        return list(full_secrets.data.data)

    def _parse_secret(self, secret: Any) -> tuple[str, CredentialsDict] | None:
        """Parse a BWS secret into (url, CredentialsDict). Returns None if invalid."""
        try:
            data = json.loads(secret.value)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[BitwardenVault] Skipping secret '{secret.key}': invalid JSON value")
            return None

        url = data.get("url")
        password = data.get("password")
        if not url or not password:
            logger.warning(f"[BitwardenVault] Skipping secret '{secret.key}': missing url or password")
            return None

        creds: CredentialsDict = {"password": password}
        if data.get("username"):
            creds["username"] = data["username"]
        if data.get("email"):
            creds["email"] = data["email"]
        if data.get("mfa_secret"):
            creds["mfa_secret"] = data["mfa_secret"]
        return url, creds

    @override
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        secrets = self._secrets_cache if self._secrets_cache is not None else self._fetch_secrets()
        target_domain = get_root_domain(url)
        for secret in secrets:
            parsed = self._parse_secret(secret)
            if parsed is None:
                continue
            secret_url, creds = parsed
            if get_root_domain(secret_url) == target_domain:
                return creds
        return None

    @override
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        assert self._client is not None
        if not self._organization_id:
            raise ValueError("organization_id required to add credentials")
        if not self._project_id:
            raise ValueError("project_id required to add credentials")
        value = json.dumps({"url": url, **creds})
        _ = self._client.secrets().create(
            uuid.UUID(self._organization_id),
            url,
            value,
            None,
            [uuid.UUID(self._project_id)],
        )
        self._secrets_cache = None

    @override
    async def delete_credentials_async(self, url: str) -> None:
        assert self._client is not None
        secrets = self._secrets_cache if self._secrets_cache is not None else self._fetch_secrets()
        target_domain = get_root_domain(url)
        for secret in secrets:
            parsed = self._parse_secret(secret)
            if parsed is None:
                continue
            secret_url, _ = parsed
            if get_root_domain(secret_url) == target_domain:
                _ = self._client.secrets().delete([secret.id])
                self._secrets_cache = None
                return
        raise ValueError(f"No credentials found for {url}")

    @override
    async def list_credentials_async(self) -> list[Credential]:
        secrets = self._secrets_cache if self._secrets_cache is not None else self._fetch_secrets()
        credentials: list[Credential] = []
        for secret in secrets:
            parsed = self._parse_secret(secret)
            if parsed is None:
                continue
            secret_url, creds = parsed
            credentials.append(
                Credential(
                    url=secret_url,
                    username=creds.get("username"),
                    email=creds.get("email"),
                )
            )
        return credentials

    @override
    async def set_credit_card_async(self, **kwargs: Unpack[CreditCardDict]) -> None:
        raise NotImplementedError("Credit card storage not supported in BitwardenVault")

    @override
    async def get_credit_card_async(self) -> CreditCardDict:
        raise NotImplementedError("Credit card storage not supported in BitwardenVault")

    @override
    async def delete_credit_card_async(self) -> None:
        raise NotImplementedError("Credit card storage not supported in BitwardenVault")
