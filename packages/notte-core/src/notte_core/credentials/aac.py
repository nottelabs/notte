from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from typing import Unpack

import pyotp
from pydantic import BaseModel, ValidationError
from typing_extensions import override

from notte_core.credentials.base import BaseVault, Credential, CredentialsDict, CreditCardDict
from notte_core.logging import logger
from notte_core.resource import SyncResource
from notte_core.url import get_root_domain


class _AacError(BaseModel):
    code: str
    message: str


class _AacCredential(BaseModel):
    username: str | None = None
    password: str | None = None
    totp: str | None = None


class _AacResponse(BaseModel):
    """Output of `aac connect --domain ... --output json` (aac v0.11.0)."""

    success: bool
    credential: _AacCredential | None = None
    error: _AacError | None = None


class AacVault(BaseVault, SyncResource):
    """Vault backed by the Agent Access Protocol (`aac` CLI, https://github.com/bitwarden/agent-access).

    Credentials are requested per domain through an end-to-end encrypted tunnel to the user's
    credential provider (e.g. Bitwarden Password Manager), when a fill action needs them. They are
    never bulk-loaded or persisted.

    The user runs `aac listen` on their machine and shares the pairing token it prints. The first
    credential request pairs with that token; later requests reuse the connection `aac` caches.

        with AacVault(token="ABC-DEF-GHI") as vault, notte.Session(vault=vault) as session:
            session.execute(type="goto", url="https://github.com/login")
            session.execute(type="form_fill", value={"username": notte.USERNAME, "current_password": notte.PASSWORD})
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
            token: Rendezvous code (ABC-DEF-GHI) or PSK token printed by `aac listen`. Defaults to the
                `AAC_TOKEN` env var. Without a token, a connection cached by `aac` is used.
            proxy_url: WebSocket URL of the aac proxy server.
            session: Hex fingerprint (or unique prefix) of the cached connection to use when no token is
                given. Required when `aac` has cached more than one connection.
            timeout: Seconds to wait for the user's provider to answer a credential request.
            aac_path: Path to the aac CLI binary.
        """
        super().__init__()
        self.token: str | None = token or os.environ.get("AAC_TOKEN")
        self.proxy_url: str = proxy_url
        self._session: str | None = session
        self._timeout: int = timeout
        self._aac_path: str = aac_path

    @override
    def start(self) -> None:
        if shutil.which(self._aac_path) is None:
            raise RuntimeError(
                f"'{self._aac_path}' CLI not found. Install from: https://github.com/bitwarden/agent-access/releases"
            )

    @override
    def stop(self) -> None:
        pass

    def _request_credential(self, domain: str) -> _AacCredential | None:
        """Request the credential for `domain` through the tunnel, pairing first if a token is pending."""
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
        # `--token` and `--session` are mutually exclusive in `aac connect`
        if self.token:
            cmd.extend(["--token", self.token])
        elif self._session:
            cmd.extend(["--session", self._session])

        try:
            # the pairing handshake comes on top of the credential timeout
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout + 30, check=False)  # noqa: S603
        except subprocess.TimeoutExpired:
            logger.warning(f"[AacVault] Credential request for {domain} timed out")
            return None

        # stdout may hold the credential, so it never goes into a log message
        try:
            response = _AacResponse.model_validate_json(result.stdout)
        except ValidationError:
            response = None
        error = None if response is None else response.error
        if response is not None and (response.success or (error is not None and error.code == "credential_not_found")):
            # paired: `aac` cached the connection, and a rendezvous code only works once
            self.token = None
        if result.returncode != 0 or response is None or not response.success or response.credential is None:
            message = (
                error.message if error is not None else (result.stderr.strip() or f"exit code {result.returncode}")
            )
            logger.warning(f"[AacVault] Credential request failed for {domain}: {message}")
            return None
        return response.credential

    @override
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        domain = get_root_domain(url)
        if not domain:
            return None

        cred = await asyncio.to_thread(self._request_credential, domain)
        if cred is None or not cred.password:
            return None

        result: CredentialsDict = {"password": cred.password}
        if cred.username:
            result["username"] = cred.username
        if cred.totp:
            # providers return the TOTP seed, either base32 or an otpauth:// URI; the base vault turns it into a code
            result["mfa_secret"] = (
                pyotp.parse_uri(cred.totp).secret if cred.totp.startswith("otpauth://") else cred.totp
            )
        return result

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
