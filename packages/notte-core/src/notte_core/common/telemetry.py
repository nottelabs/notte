import importlib.metadata as metadata
import logging
import os
import platform
import uuid
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

import posthog

logger = logging.getLogger("notte.telemetry")

try:
    __version__ = metadata.version("notte")
except Exception:
    __version__ = "unknown"

TELEMETRY_ENABLED: bool = os.environ.get("ANONYMIZED_TELEMETRY", "true").lower() == "true"

TELEMETRY_DIR = Path.home() / ".cache" / "notte"
USER_ID_PATH = TELEMETRY_DIR / "telemetry_user_id"


def get_or_create_installation_id() -> str:
    """Get existing installation ID or create and save a new one."""
    if USER_ID_PATH.exists():
        return USER_ID_PATH.read_text().strip()

    installation_id = str(uuid.uuid4())
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
    _ = USER_ID_PATH.write_text(installation_id)  # Assign to _ to acknowledge unused result
    return installation_id


INSTALLATION_ID: str = get_or_create_installation_id()
POSTHOG_API_KEY: str = "phc_xoTxeXSFaLC4jc3qmWrmnolLtTrcIkzf4m6zME1fvQC"  # pragma: allowlist secret
POSTHOG_HOST: str = "https://us.i.posthog.com"

F = TypeVar("F", bound=Callable[..., Any])

DEBUG_LOGGING = os.environ.get("NOTTE_LOGGING_LEVEL", "info").lower() == "debug"

POSTHOG_EVENT_SETTINGS = {
    "process_person_profile": True,
}


class BaseTelemetryEvent:
    """Base class for telemetry events"""

    name: str  # Add type annotation
    properties: dict[str, Any]  # Add type annotation

    def __init__(self, name: str, properties: dict[str, Any] | None = None):
        self.name = name
        self.properties = properties or {}


def setup_posthog() -> Any | None:
    """Set up the PostHog client if enabled."""
    if not TELEMETRY_ENABLED:
        return None

    try:
        client: Any = posthog.Posthog(
            api_key=POSTHOG_API_KEY,
            host=POSTHOG_HOST,
            disable_geoip=False,
        )

        if not DEBUG_LOGGING:
            posthog_logger = logging.getLogger("posthog")
            posthog_logger.disabled = True

        return client
    except Exception as e:
        logger.debug(f"Failed to initialize PostHog: {e}")
        return None


posthog_client = setup_posthog()


def get_system_info() -> dict[str, Any]:
    """Get anonymous system information."""
    return {
        "os": platform.system(),
        "python_version": platform.python_version(),
        "notte_version": __version__,
    }


def capture_event(event_name: str, properties: dict[str, Any] | None = None) -> None:
    """Capture an event if telemetry is enabled."""
    if not TELEMETRY_ENABLED or posthog_client is None:
        return

    try:
        event_properties = properties or {}
        event_properties.update(get_system_info())
        event_properties.update(POSTHOG_EVENT_SETTINGS)

        if DEBUG_LOGGING:
            logger.debug(f"Telemetry event: {event_name} {event_properties}")

        posthog_client.capture(distinct_id=INSTALLATION_ID, event=event_name, properties=event_properties)
    except Exception as e:
        logger.error(f"Failed to send telemetry event {event_name}: {e}")


def track_usage(method_name: str | None = None) -> Callable[[F], F]:
    """Decorator to track usage of a method."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            event_name = method_name if method_name is not None else f"{func.__module__}.{func.__name__}"
            capture_event(f"method.called.{event_name}", {"args": args, "kwargs": kwargs})
            result = func(*args, **kwargs)
            return result

        return wrapper  # type: ignore

    return decorator
