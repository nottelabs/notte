from dataclasses import dataclass


@dataclass
class Credentials:
    url: str
    username: str
    password: str
