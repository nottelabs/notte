import os
from collections.abc import Mapping
from dataclasses import dataclass


def _read_bounded_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw_value!r}") from exc

    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def _read_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized_value = raw_value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean, got {raw_value!r}")


@dataclass(frozen=True)
class AkamaiSoftDenyRecoveryPolicy:
    enabled: bool
    max_reloads: int
    settle_ms: int

    @classmethod
    def from_env(cls) -> "AkamaiSoftDenyRecoveryPolicy":
        return cls(
            enabled=_read_bool("AKAMAI_SOFT_DENY_RECOVERY_ENABLED", False),
            max_reloads=_read_bounded_int("AKAMAI_SOFT_DENY_MAX_RELOADS", 3, minimum=0, maximum=5),
            settle_ms=_read_bounded_int("AKAMAI_SOFT_DENY_SETTLE_MS", 3000, minimum=500, maximum=10000),
        )


AKAMAI_SOFT_DENY_RECOVERY_POLICY = AkamaiSoftDenyRecoveryPolicy.from_env()


def is_akamai_soft_deny(*, status: int, headers: Mapping[str, str], body: str) -> bool:
    if status != 403:
        return False

    normalized_headers = {name.lower(): value.lower() for name, value in headers.items()}
    if "text/html" not in normalized_headers.get("content-type", ""):
        return False
    if "x-akamai-transformed" not in normalized_headers:
        return False

    normalized_body = body.lower()
    return all(
        marker in normalized_body
        for marker in (
            "access denied",
            "you don't have permission",
            "errors.edgesuite.net",
        )
    )
