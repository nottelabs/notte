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


class AacVault(BaseVault, SyncResource):
    """Vault backed by the Agent Access Protocol (aac).

    Fetches credentials on-demand through an E2E encrypted Noise tunnel
    via Bitwarden's proxy. Works with any aac-compatible credential provider
    (Bitwarden Password Manager, 1Password, etc.).

    Credentials are requested per-domain when the agent encounters a login
    form — never bulk-loaded, never persisted.

    The user must be running `aac listen` on their machine for this vault
    to function.
    """

    def __init__(
        self,
        token: str | None = None,
        proxy_url: str = "wss://ap.lesspassword.dev",
        session: str | None = None,
        timeout: int = 120,
        aac_path: str = "aac",
    ):
        """
        Args:
            token: Rendezvous code (ABC-DEF-GHI) or PSK token for pairing.
                   If None, uses a cached session.
            proxy_url: WebSocket URL of the aac proxy server.
            session: Hex fingerprint (or prefix) of a cached session to use.
                     If None and no token, auto-selects the single cached session.
            timeout: Timeout in seconds for credential responses.
            aac_path: Path to the aac CLI binary.
        """
        super().__init__()
        self.token: str | None = token or os.environ.get("AAC_TOKEN")
        self.proxy_url: str = proxy_url
        self._session: str | None = session
        self._timeout: int = timeout
        self._aac_path: str = aac_path
        self._paired: bool = False

    @override
    def start(self) -> None:
        if shutil.which(self._aac_path) is None:
            raise RuntimeError(
                f"'{self._aac_path}' CLI not found. Install from: https://github.com/bitwarden/agent-access/releases"
            )
        if self.token:
            self._pair()

    @override
    def stop(self) -> None:
        self._paired = False

    def _pair(self) -> None:
        """Establish the E2E tunnel by pairing with the user's aac listen."""
        assert self.token is not None
        cmd: list[str] = [
            self._aac_path,
            "connect",
            "--token",
            self.token,
            "--proxy-url",
            self.proxy_url,
            "--output",
            "json",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)  # noqa: S603
        if result.returncode != 0:
            try:
                data = json.loads(result.stdout)
                msg = data.get("error", {}).get("message", result.stderr)
            except (json.JSONDecodeError, TypeError):
                msg = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"aac pairing failed: {msg}")

        try:
            data = json.loads(result.stdout)
            if not data.get("success"):
                msg = data.get("error", {}).get("message", result.stdout.strip())
                raise RuntimeError(f"aac pairing failed: {msg}")
        except (json.JSONDecodeError, TypeError):
            pass

        self._paired = True
        logger.info("[AacVault] Paired successfully via aac tunnel")

    def _request_credential(self, domain: str) -> dict[str, str | None] | None:
        """Request a single credential through the E2E tunnel."""
        cmd: list[str] = [
            self._aac_path,
            "connect",
            "--domain",
            domain,
            "--proxy-url",
            self.proxy_url,
            "--output",
            "json",
            "--timeout",
            str(self._timeout),
        ]
        if self._session:
            cmd.extend(["--session", self._session])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout + 10)  # noqa: S603
        if result.returncode != 0:
            try:
                data = json.loads(result.stdout)
                msg = data.get("error", {}).get("message", "unknown error")
            except (json.JSONDecodeError, TypeError):
                msg = result.stderr.strip() or f"exit code {result.returncode}"
            logger.warning(f"[AacVault] Credential request failed for {domain}: {msg}")
            return None

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning(f"[AacVault] Invalid JSON response for {domain}")
            return None

        if not data.get("success"):
            return None

        return data.get("credential")

    @override
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        domain = get_root_domain(url)
        if not domain:
            return None

        cred = self._request_credential(domain)
        if cred is None:
            return None

        password = cred.get("password")
        if not password:
            return None

        result: CredentialsDict = {"password": password}
        username = cred.get("username")
        if username:
            result["username"] = username
        totp = cred.get("totp")
        if totp:
            result["mfa_secret"] = totp
        return result

    @override
    async def get_credentials_async(self, url: str) -> CredentialsDict | None:
        """Override to bypass TOTP generation — aac returns live codes, not secrets."""
        credentials = await self._get_credentials_impl(url)
        if credentials is None:
            return None
        # Track retrieved credentials for screenshot masking
        self._retrieved_credentials[url] = credentials
        return credentials

    @override
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        raise NotImplementedError("aac is read-only — manage credentials in your vault app")

    @override
    async def delete_credentials_async(self, url: str) -> None:
        raise NotImplementedError("aac is read-only — manage credentials in your vault app")

    @override
    async def list_credentials_async(self) -> list[Credential]:
        return []

    @override
    async def set_credit_card_async(self, **kwargs: Unpack[CreditCardDict]) -> None:
        raise NotImplementedError("Credit card not supported via aac")

    @override
    async def get_credit_card_async(self) -> CreditCardDict:
        raise NotImplementedError("Credit card not supported via aac")

    @override
    async def delete_credit_card_async(self) -> None:
        raise NotImplementedError("Credit card not supported via aac")
