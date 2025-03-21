from typing_extensions import TypedDict


class ProxySettings(TypedDict, total=False):
    server: str
    bypass: str | None
    username: str | None
    password: str | None
