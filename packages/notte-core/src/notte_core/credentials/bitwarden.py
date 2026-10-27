from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Unpack

from pydantic import BaseModel, ValidationError
from typing_extensions import override

from notte_core.credentials.base import BaseVault, Credential, CredentialsDict, CreditCardDict
from notte_core.logging import logger
from notte_core.resource import SyncResource
from notte_core.url import get_root_domain

if TYPE_CHECKING:
    from bitwarden_sdk import BitwardenClient, SecretResponse  # pyright: ignore[reportMissingTypeStubs]


class _SecretValue(BaseModel):
    """The JSON value of a Bitwarden secret holding a notte credential."""

    url: str
    password: str
    username: str | None = None
    email: str | None = None
    mfa_secret: str | None = None


class BitwardenVault(BaseVault, SyncResource):
    """Vault backed by Bitwarden Secrets Manager, through the official Python SDK.

    Requires the `bitwarden` extra: `pip install "notte-core[bitwarden]"`.

    Each secret's value must be a JSON object in the notte credential format:
    {"url": "https://...", "password": "...", "username": "...", "email": "...", "mfa_secret": "..."}
    Only `url` and `password` are required. Secrets are matched to pages by root domain.
    Exact URL matches take precedence. Deletion rejects multiple matches rather than choosing a secret.

        with BitwardenVault() as vault, notte.Session(vault=vault) as session:
            session.execute(type="goto", url="https://github.com/login")
            session.execute(type="form_fill", value={"username": notte.USERNAME, "current_password": notte.PASSWORD})
    """

    def __init__(
        self,
        access_token: str | None = None,
        organization_id: str | None = None,
        project_id: str | None = None,
        api_url: str = "https://api.bitwarden.com",
        identity_url: str = "https://identity.bitwarden.com",
    ):
        """
        Args:
            access_token: Machine account access token. Defaults to the `BWS_ACCESS_TOKEN` env var.
            organization_id: Organization whose secrets are read. Defaults to the `BWS_ORGANIZATION_ID` env var.
            project_id: Project new credentials are added to. Only needed by `add_credentials`.
            api_url: Bitwarden API URL (for self-hosted or EU instances).
            identity_url: Bitwarden identity URL (for self-hosted or EU instances).
        """
        super().__init__()
        self._access_token: str = access_token or os.environ.get("BWS_ACCESS_TOKEN", "")
        self._organization_id: str | None = organization_id or os.environ.get("BWS_ORGANIZATION_ID")
        self._project_id: str | None = project_id
        self._api_url: str = api_url
        self._identity_url: str = identity_url
        self._client: BitwardenClient | None = None
        self._secrets_cache: list[SecretResponse] | None = None
        self._cache_generation: int = 0

    @override
    def start(self) -> None:
        if not self._access_token:
            raise ValueError("Bitwarden access token required. Set BWS_ACCESS_TOKEN env var or pass access_token=")
        if not self._organization_id:
            raise ValueError(
                "Bitwarden organization id required. Set BWS_ORGANIZATION_ID env var or pass organization_id="
            )

        try:
            from bitwarden_sdk import (  # pyright: ignore[reportMissingTypeStubs]
                BitwardenClient,
                ClientSettings,
                DeviceType,
            )
        except ImportError:
            raise ImportError(
                'bitwarden-sdk is required for BitwardenVault. Install it with: pip install "notte-core[bitwarden]"'
            ) from None

        client = BitwardenClient(
            ClientSettings(
                api_url=self._api_url,
                identity_url=self._identity_url,
                device_type=DeviceType.SDK,
                user_agent="notte",
            )
        )
        _ = client.auth().login_access_token(self._access_token)
        self._client = client
        self._invalidate_secrets()
        self._secrets_cache = self._fetch_secrets()
        logger.info(f"[BitwardenVault] Loaded {len(self._secrets_cache)} secrets")

    @override
    def stop(self) -> None:
        self._client = None
        self._invalidate_secrets()

    def _invalidate_secrets(self) -> None:
        self._cache_generation += 1
        self._secrets_cache = None

    async def _write(self, write: Callable[[], None]) -> None:
        """Finish a native write and invalidate its cache before propagating cancellation."""
        task = asyncio.create_task(asyncio.to_thread(write))
        cancelled: asyncio.CancelledError | None = None
        while not task.done():
            try:
                _ = await asyncio.wait({task})
            except asyncio.CancelledError as error:
                cancelled = error
        error = None if task.cancelled() else task.exception()
        self._invalidate_secrets()
        if cancelled is not None:
            raise cancelled
        if error is not None:
            raise error
        task.result()

    def _require_client(self) -> BitwardenClient:
        if self._client is None:
            raise RuntimeError("BitwardenVault is not started. Use it as a context manager or call start() first.")
        return self._client

    def _fetch_secrets(self) -> list[SecretResponse]:
        client = self._require_client()
        assert self._organization_id is not None
        response = client.secrets().list(self._organization_id)
        if response.data is None or not response.data.data:
            return []
        full_secrets = client.secrets().get_by_ids([s.id for s in response.data.data])
        if full_secrets.data is None:
            return []
        return list(full_secrets.data.data)

    async def _secrets(self) -> list[SecretResponse]:
        """The organization's secrets, refetched after this vault added or deleted one."""
        while self._secrets_cache is None:
            generation = self._cache_generation
            secrets = await asyncio.to_thread(self._fetch_secrets)
            if generation == self._cache_generation:
                self._secrets_cache = secrets
        return self._secrets_cache

    @staticmethod
    def _parse_secret(secret: SecretResponse) -> tuple[str, CredentialsDict] | None:
        """Parse a secret into (url, credentials). Returns None if it is not a notte credential."""
        try:
            value = _SecretValue.model_validate_json(secret.value)
        except ValidationError:
            # the error would quote the secret's value, so only its key is logged
            logger.warning(f"[BitwardenVault] Skipping secret '{secret.key}': value is not a JSON credential")
            return None
        if not value.url or not value.password:
            logger.warning(f"[BitwardenVault] Skipping secret '{secret.key}': missing url or password")
            return None

        creds: CredentialsDict = {"password": value.password}
        if value.username:
            creds["username"] = value.username
        if value.email:
            creds["email"] = value.email
        if value.mfa_secret:
            creds["mfa_secret"] = value.mfa_secret
        return value.url, creds

    async def _find_secret(
        self, url: str, *, require_unique: bool = False
    ) -> tuple[SecretResponse, CredentialsDict] | None:
        target_domain = get_root_domain(url)
        if not target_domain:
            return None
        matches: list[tuple[SecretResponse, CredentialsDict]] = []
        exact: list[tuple[SecretResponse, CredentialsDict]] = []
        for secret in await self._secrets():
            parsed = self._parse_secret(secret)
            if parsed is not None and get_root_domain(parsed[0]) == target_domain:
                match = (secret, parsed[1])
                matches.append(match)
                if parsed[0] == url:
                    exact.append(match)
        candidates = exact or matches
        if require_unique and len(candidates) > 1:
            raise ValueError(f"Ambiguous credentials for {url}: multiple secrets match")
        return candidates[0] if candidates else None

    @override
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        found = await self._find_secret(url)
        return None if found is None else found[1]

    @override
    async def has_credential_async(self, url: str) -> bool:
        return await self._find_secret(url) is not None

    @override
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        client = self._require_client()
        assert self._organization_id is not None
        if not self._project_id:
            raise ValueError("project_id required to add credentials")
        organization_id = uuid.UUID(self._organization_id)
        project_id = uuid.UUID(self._project_id)

        def create() -> None:
            _ = client.secrets().create(organization_id, url, json.dumps({"url": url, **creds}), None, [project_id])

        await self._write(create)

    @override
    async def delete_credentials_async(self, url: str) -> None:
        client = self._require_client()
        found = await self._find_secret(url, require_unique=True)
        if found is None:
            raise ValueError(f"No credentials found for {url}")
        secret_id = str(found[0].id)

        def delete() -> None:
            _ = client.secrets().delete([secret_id])

        await self._write(delete)

    @override
    async def list_credentials_async(self) -> list[Credential]:
        credentials: list[Credential] = []
        for secret in await self._secrets():
            parsed = self._parse_secret(secret)
            if parsed is None:
                continue
            secret_url, creds = parsed
            credentials.append(Credential(url=secret_url, username=creds.get("username"), email=creds.get("email")))
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
