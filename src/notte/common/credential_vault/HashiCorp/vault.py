from dataclasses import dataclass
from typing import Any, Protocol, final
from urllib.parse import urlparse

from typing_extensions import override

from notte.common.credential_vault.base import BaseVault, VaultCredentials


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
                " Install it with 'poetry install --with vault'"
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

    @override
    def add_credentials(self, url: str, username: str, password: str) -> None:
        domain = urlparse(url).netloc or url
        self.secrets.create_or_update_secret(
            path=f"credentials/{domain}",
            secret=dict(url=url, username=username, password=password),
            mount_point=self._mount_path,
        )

    @override
    def get_credentials(self, url: str) -> VaultCredentials | None:
        domain = urlparse(url).netloc or url
        try:
            secret = self.secrets.read_secret_version(path=f"credentials/{domain}", mount_point=self._mount_path)
            data = secret["data"]["data"]
            return VaultCredentials(url=data["url"], username=data["username"], password=data["password"])
        except Exception:
            return None

    @override
    def remove_credentials(self, url: str) -> None:
        domain = urlparse(url).netloc or url
        self.secrets.delete_metadata_and_all_versions(path=f"credentials/{domain}", mount_point=self._mount_path)
