from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Unpack

from typing_extensions import override

from notte_core.common.logging import logger
from notte_core.common.resource import SyncResource
from notte_core.credentials.base import BaseVault, Credential, CredentialsDict, CreditCardDict
from notte_core.utils.url import get_root_domain


class BitwardenVault(BaseVault, SyncResource):
    """Vault backed by Bitwarden Secrets Manager via the `bws` CLI.

    Credentials are fetched from a Bitwarden Secrets Manager project.
    Each secret's value must be a JSON object with the notte credential format:
    {"url": "https://...", "password": "...", "username": "...", "email": "...", "mfa_secret": "..."}

    Only `url` and `password` are required.
    """

    def __init__(
        self,
        access_token: str | None = None,
        project_id: str | None = None,
        bws_path: str = "bws",
        timeout: int = 30,
    ):
        super().__init__()
        self._access_token: str = access_token or os.environ.get("BWS_ACCESS_TOKEN", "")
        self._project_id: str | None = project_id
        self._bws_path: str = bws_path
        self._timeout: int = timeout
        self._secrets_cache: list[dict[str, str]] | None = None

    @override
    def start(self) -> None:
        if shutil.which(self._bws_path) is None:
            raise RuntimeError(
                f"'{self._bws_path}' CLI not found. Install it from: https://github.com/bitwarden/sdk/releases"
            )
        if not self._access_token:
            raise ValueError("Bitwarden access token required. Set BWS_ACCESS_TOKEN env var or pass access_token=")
        self._secrets_cache = self._fetch_secrets()
        logger.info(f"[BitwardenVault] Loaded {len(self._secrets_cache)} secrets")

    @override
    def stop(self) -> None:
        self._secrets_cache = None

    def _run_bws(self, *args: str) -> str:
        cmd = [self._bws_path] + list(args) + ["--output", "json"]
        env = {**os.environ, "BWS_ACCESS_TOKEN": self._access_token}
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=self._timeout)  # noqa: S603
        if result.returncode != 0:
            raise RuntimeError(f"bws command failed: {result.stderr.strip()}")
        return result.stdout

    def _fetch_secrets(self) -> list[dict[str, str]]:
        args = ["secret", "list"]
        if self._project_id:
            args.append(self._project_id)
        raw = self._run_bws(*args)
        return json.loads(raw)

    def _parse_secret_value(self, secret: dict[str, str]) -> tuple[str, CredentialsDict] | None:
        """Parse a BWS secret into (url, CredentialsDict). Returns None if invalid."""
        try:
            data = json.loads(secret.get("value", ""))
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[BitwardenVault] Skipping secret '{secret.get('key')}': invalid JSON value")
            return None

        url = data.get("url")
        password = data.get("password")
        if not url or not password:
            logger.warning(f"[BitwardenVault] Skipping secret '{secret.get('key')}': missing url or password")
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
        secrets = self._secrets_cache or self._fetch_secrets()
        target_domain = get_root_domain(url)
        for secret in secrets:
            parsed = self._parse_secret_value(secret)
            if parsed is None:
                continue
            secret_url, creds = parsed
            if get_root_domain(secret_url) == target_domain:
                return creds
        return None

    @override
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        if not self._project_id:
            raise ValueError("project_id required to add credentials")
        value = json.dumps({"url": url, **creds})
        _ = self._run_bws("secret", "create", url, value, self._project_id)
        self._secrets_cache = None

    @override
    async def delete_credentials_async(self, url: str) -> None:
        secrets = self._secrets_cache or self._fetch_secrets()
        target_domain = get_root_domain(url)
        for secret in secrets:
            parsed = self._parse_secret_value(secret)
            if parsed is None:
                continue
            secret_url, _ = parsed
            if get_root_domain(secret_url) == target_domain:
                _ = self._run_bws("secret", "delete", secret["id"])
                self._secrets_cache = None
                return
        raise ValueError(f"No credentials found for {url}")

    @override
    async def list_credentials_async(self) -> list[Credential]:
        secrets = self._secrets_cache or self._fetch_secrets()
        credentials: list[Credential] = []
        for secret in secrets:
            parsed = self._parse_secret_value(secret)
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
