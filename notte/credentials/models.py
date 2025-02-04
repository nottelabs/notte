from dataclasses import dataclass
from typing import Dict, Optional, Protocol


@dataclass
class Credentials:
    url: str
    username: str
    password: str


class VaultInterface(Protocol):
    def add_credentials(self, url: str, username: str, password: str) -> None:
        """Store credentials for a given URL"""
        ...

    def get_credentials(self, url: str) -> Optional[Credentials]:
        """Retrieve credentials for a given URL"""
        ...

    def remove_credentials(self, url: str) -> None:
        """Remove credentials for a given URL"""
        ...

    def replace_placeholder_credentials(
        self, url: str | None, params: Dict[str, str] | str | None
    ) -> Dict[str, str] | str | None:
        """Replace placeholder credentials with actual credentials"""
        ...
