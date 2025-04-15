import os
from dataclasses import dataclass
from typing import Any, Protocol, final

import tldextract
from hvac.exceptions import InvalidPath
from notte_core.credentials.base import (
    BaseVault,
    CredentialField,
    VaultCredentials,
)
from typing_extensions import override


class SysProtocol(Protocol):
    def list_mounted_secrets_engines(self) -> Any: ...
    def enable_secrets_engine(self, backend_type: str, path: str, options: dict[str, Any]) -> Any: ...


class SecretsProtocol(Protocol):
    def read_secret_version(self, path: str, mount_point: str) -> Any: ...
    def create_or_update_secret(self, path: str, secret: dict[str, Any], mount_point: str) -> Any: ...
    def delete_metadata_and_all_versions(self, path: str, mount_point: str) -> Any: ...


@dataclass
class HashiCorpVaultClientProtocol:
    url: str
    token: str
    sys: SysProtocol


try:
    from hvac import Client as HashiCorpVaultClient

    VAULT_AVAILABLE = True
except ImportError:
    VAULT_AVAILABLE = False  # type: ignore


def check_vault_imports():
    if not VAULT_AVAILABLE:
        raise ImportError(
            (
                "The 'hvac' package is required for HashiCorp Vault integration."
                " Install 'vault' optional dependencies with 'uv sync --extra vault'"
            )
        )


@final
class HashiCorpVault(BaseVault):
    """HashiCorp Vault implementation of the BaseVault interface."""

    def __init__(self, url: str, token: str):
        check_vault_imports()
        self.client: HashiCorpVaultClientProtocol = HashiCorpVaultClient(url=url, token=token)  # type: ignore
        self.secrets: SecretsProtocol = self.client.secrets.kv.v2  # type: ignore
        self._mount_path: str = "secret"
        self._init_vault()

    def _init_vault(self) -> None:
        try:
            mounts = self.client.sys.list_mounted_secrets_engines()
            if self._mount_path not in mounts["data"]:
                self.client.sys.enable_secrets_engine(
                    backend_type="kv", path=self._mount_path, options={"version": "2"}
                )
            else:
                mount_info = mounts["data"][f"{self._mount_path}/"]["options"]
                if mount_info.get("version") != "2":
                    raise ValueError(f"Existing {self._mount_path} mount is not a KV v2 secrets engine")
        except Exception as e:
            if "path is already in use" not in str(e):
                raise e

    @staticmethod
    def get_root_domain(url: str) -> str:
        return tldextract.extract(url).domain or url

    @override
    async def _set_singleton_credentials(self, creds: list[CredentialField]) -> None:
        for cred in creds:
            if not cred.singleton:
                raise ValueError(f"{cred.__class__} can't be set as singleton credential: url-specific only")

        self.secrets.create_or_update_secret(
            path="singleton_credentials",
            secret=dict(
                **{cred.__class__.__qualname__: cred.value for cred in creds},
            ),
            mount_point=self._mount_path,
        )

    @override
    async def get_singleton_credentials(self) -> list[CredentialField]:
        try:
            secret = self.secrets.read_secret_version(path="singleton_credentials", mount_point=self._mount_path)
        except InvalidPath:
            return []

        data = secret["data"]["data"]

        return [CredentialField.registry[key](value=value) for key, value in data.items()]

    @override
    async def _add_credentials(self, creds: VaultCredentials) -> None:
        for cred in creds.creds:
            if cred.singleton:
                raise ValueError(f"{cred.__class__} can't be set as url specific credential: singleton only")
        domain = HashiCorpVault.get_root_domain(creds.url)
        self.secrets.create_or_update_secret(
            path=f"credentials/{domain}",
            secret=dict(
                url=creds.url,
                **{cred.__class__.__qualname__: cred.value for cred in creds.creds},
            ),
            mount_point=self._mount_path,
        )

    @override
    async def _get_credentials_impl(self, url: str) -> VaultCredentials | None:
        domain = HashiCorpVault.get_root_domain(url)
        try:
            secret = self.secrets.read_secret_version(path=f"credentials/{domain}", mount_point=self._mount_path)
            data = secret["data"]["data"]
            url = data["url"]
            del data["url"]

            return VaultCredentials(
                url=url,
                creds=[CredentialField.registry[key](value=value) for key, value in data.items()],
            )

        except Exception:
            return None

    @override
    async def remove_credentials(self, url: str) -> None:
        domain = HashiCorpVault.get_root_domain(url)
        self.secrets.delete_metadata_and_all_versions(path=f"credentials/{domain}", mount_point=self._mount_path)

    @classmethod
    def create_from_env(cls) -> "HashiCorpVault":
        """Create a HashiCorpVault instance from environment variables.

        Requires VAULT_URL and VAULT_DEV_ROOT_TOKEN_ID to be set in environment variables.
        Automatically loads from .env file if present.

        Returns:
            HashiCorpVault: Initialized vault instance

        Raises:
            ValueError: If required environment variables are missing or vault server is not running
        """
        vault_url = os.getenv("VAULT_URL")
        vault_token = os.getenv("VAULT_DEV_ROOT_TOKEN_ID")

        if not vault_url or not vault_token:
            raise ValueError(
                """"
VAULT_URL and VAULT_DEV_ROOT_TOKEN_ID must be set in the .env file.
For example if you are running the vault locally:
VAULT_URL=http://0.0.0.0:8200
VAULT_DEV_ROOT_TOKEN_ID=<your-vault-dev-root-token-id>
"""
            )

        try:
            return cls(url=vault_url, token=vault_token)
        except ConnectionError as e:
            vault_not_running_instructions = """
Make sure to start the vault server before running the agent.
Instructions to start the vault server:
> cd packages/notte-integrations/src/notte_integrations/credentials/hashicorp
> docker-compose --env-file ../../../../../.env up
"""
            raise ValueError(f"Vault server is not running. {vault_not_running_instructions}") from e
