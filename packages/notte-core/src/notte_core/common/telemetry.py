import importlib.metadata as metadata
import inspect
import logging
import os
import platform
import uuid
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

import posthog
from packaging import version
from scarf.event_logger import ScarfEventLogger  # pyright: ignore[reportMissingTypeStubs]

from notte_core.common.cache import CacheDirectory, ensure_cache_directory

logger = logging.getLogger("notte.telemetry")

try:
    __version__ = metadata.version("notte_core")
except Exception:
    __version__ = "unknown"


def _get_telemetry_dir() -> Path:
    """Get telemetry cache directory with XDG_CACHE_HOME override support."""
    # Check for XDG_CACHE_HOME override for backward compatibility
    env_var: str | None = os.getenv("XDG_CACHE_HOME")
    if env_var and (path := Path(env_var)).is_absolute():
        # Use XDG_CACHE_HOME/notte/.cache/telemetry/ to maintain structure
        telemetry_path = path / "notte" / ".cache" / CacheDirectory.TELEMETRY.value
        telemetry_path.mkdir(parents=True, exist_ok=True)
        return telemetry_path

    # Use centralized cache directory
    return ensure_cache_directory(CacheDirectory.TELEMETRY)


DISABLE_TELEMETRY: bool = os.environ.get("DISABLE_TELEMETRY", "false").lower() == "true"
TELEMETRY_DIR = _get_telemetry_dir()
USER_ID_PATH = TELEMETRY_DIR / "telemetry_user_id"
VERSION_DOWNLOAD_PATH = TELEMETRY_DIR / "download_version"
POSTHOG_API_KEY: str = "phc_6U4lU1RMI2hyj9DREkuyPFFDg95b0LYkoeaZ0LfaeVb"  # pragma: allowlist secret
POSTHOG_HOST: str = "https://us.i.posthog.com"
SCARF_GATEWAY_URL = "https://scarf.notte.cc/events"

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
    if DISABLE_TELEMETRY:
        return None

    try:
        client: Any = posthog.Posthog(
            project_api_key=POSTHOG_API_KEY,
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


def setup_scarf() -> Any | None:
    """Set up the Scarf client if enabled."""
    if DISABLE_TELEMETRY:
        return None

    # Initialize Scarf
    try:
        client: Any = ScarfEventLogger(
            endpoint_url=SCARF_GATEWAY_URL,
            timeout=3.0,
            verbose=DEBUG_LOGGING,
        )

        # Silence scarf's logging unless debug mode (level 2)
        if not DEBUG_LOGGING:
            scarf_logger = logging.getLogger("scarf")
            scarf_logger.disabled = True

        return client

    except Exception as e:
        logger.warning(f"Failed to initialize Scarf telemetry: {e}")
        return None


def track_package_download(installation_id: str, properties: dict[str, Any] | None = None) -> None:
    """Track package download event specifically for Scarf analytics"""
    if DISABLE_TELEMETRY:
        return None

    if scarf_client is not None:
        try:
            current_version = __version__
            should_track = False
            first_download = False

            # Check if version file exists
            if not os.path.exists(VERSION_DOWNLOAD_PATH):
                # First download
                should_track = True
                first_download = True

                # Save version (directory already created by ensure_cache_directory)
                with open(VERSION_DOWNLOAD_PATH, "w") as f:
                    _ = f.write(current_version)
            else:
                # Read saved version
                with open(VERSION_DOWNLOAD_PATH) as f:
                    saved_version = f.read().strip()

                # Compare versions (simple string comparison for now)
                if version.parse(current_version) > version.parse(saved_version):
                    should_track = True
                    first_download = False

                    # Update saved version
                    with open(VERSION_DOWNLOAD_PATH, "w") as f:
                        _ = f.write(current_version)

            if should_track:
                logger.debug(f"Tracking package download event with properties: {properties}")
                # Add package version and user_id to event
                event_properties = (properties or {}).copy()
                event_properties.update(get_system_info())
                event_properties["installation_id"] = installation_id
                event_properties["event"] = "package_download"
                event_properties["first_download"] = first_download

                # Convert complex types to simple types for Scarf compatibility
                scarf_client.log_event(properties=event_properties)
        except Exception as e:
            logger.debug(f"Failed to track Scarf package_download event: {e}")


def get_or_create_installation_id() -> str:
    """Get existing installation ID or create and save a new one."""
    if DISABLE_TELEMETRY:
        return ""

    if USER_ID_PATH.exists():
        return USER_ID_PATH.read_text().strip()

    installation_id = str(uuid.uuid4())
    # TELEMETRY_DIR is already created by ensure_cache_directory
    _ = USER_ID_PATH.write_text(installation_id)  # Assign to _ to acknowledge unused result

    # Always check for version-based download tracking
    track_package_download(
        installation_id,
        {
            "triggered_by": "user_id_property",
        },
    )
    return installation_id


posthog_client = setup_posthog()
scarf_client = setup_scarf()
INSTALLATION_ID: str = get_or_create_installation_id()


def get_system_info() -> dict[str, Any]:
    """Get anonymous system information."""
    if DISABLE_TELEMETRY:
        return {}

    return {
        "os": platform.system(),
        "python_version": platform.python_version(),
        "notte_version": __version__,
    }


def capture_event(event_name: str, properties: dict[str, Any] | None = None) -> None:
    """Capture an event if telemetry is enabled."""
    if DISABLE_TELEMETRY:
        return None
    # send to posthog
    if posthog_client is not None:
        try:
            event_properties = properties or {}
            event_properties.update(get_system_info())
            event_properties.update(POSTHOG_EVENT_SETTINGS)

            if DEBUG_LOGGING:
                logger.debug(f"Telemetry event: {event_name} {event_properties}")

            posthog_client.capture(distinct_id=INSTALLATION_ID, event=event_name, properties=event_properties)
        except Exception as e:
            logger.debug(f"Failed to send telemetry event {event_name}: {e}")
    # send to scarf
    if scarf_client is not None:
        try:
            # Add package version and user_id to all events
            properties = properties or {}
            properties.update(get_system_info())
            properties["event"] = event_name
            properties["installation_id"] = INSTALLATION_ID
            scarf_client.log_event(properties=properties)
        except Exception as e:
            logger.debug(f"Failed to send telemetry event {event_name}: {e}")


def _capture_usage_event(method_name: str, error: Exception | None = None) -> None:
    # Usage-decorated calls may contain credentials, payment details, cookies, or API tokens.
    # Keep telemetry metadata-only. The unsafe error-path payload was reported in #826 by @sebastiondev.
    properties: dict[str, Any] = {"status": "error" if error is not None else "success"}
    if error is not None:
        properties["error_type"] = type(error).__name__
    capture_event(method_name, properties=properties)


def track_usage(method_name: str) -> Callable[[F], F]:
    """Track a call without including argument values or exception messages."""

    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    result = await func(*args, **kwargs)
                except Exception as e:
                    _capture_usage_event(method_name, error=e)
                    raise
                else:
                    _capture_usage_event(method_name)
                    return result

            return async_wrapper  # type: ignore

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                _capture_usage_event(method_name, error=e)
                raise
            else:
                _capture_usage_event(method_name)
                return result

        return wrapper  # type: ignore

    return decorator
