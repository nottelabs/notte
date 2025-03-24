import importlib.metadata as metadata
import logging
import os
import platform
import uuid
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger("notte.telemetry")

try:
    # Try to get the version of the package
    __version__ = metadata.version("notte")
except Exception:
    __version__ = "unknown"


TELEMETRY_ENABLED: bool = os.environ.get("ANONYMIZED_TELEMETRY", "true").lower() != "false"

# anonymous ID
INSTALLATION_ID: str = str(uuid.uuid4())


POSTHOG_API_KEY: str = os.environ.get("POSTHOG_API_KEY", "phc_your_default_key_here")

# PostHog host URL
POSTHOG_HOST: str = os.environ.get("POSTHOG_HOST", "https://app.posthog.com")


F = TypeVar("F", bound=Callable[..., Any])

# avoid unbound variable errors
posthog = None
posthog_available = False

try:
    import posthog  # type: ignore[reportMissingModuleSource]

    posthog_available = True
except (ImportError, ModuleNotFoundError):
    posthog = None  # Explicitly set to None
    logger.debug("PostHog not installed. Telemetry will be disabled.")
    posthog_available = False


def setup_posthog() -> Any | None:
    """Set up the PostHog client if enabled and available."""
    if not TELEMETRY_ENABLED or not posthog_available or posthog is None:
        return None

    try:
        # Use explicit Any type for client to resolve unknown type warnings
        # And ignore the unknown type for posthog.Posthog
        client: Any = posthog.Posthog(  # type: ignore[reportUnknownMemberType]
            api_key=POSTHOG_API_KEY,
            host=POSTHOG_HOST,
        )
        return client
    except Exception as e:
        logger.debug(f"Failed to initialize PostHog: {e}")
        return None


# Initialize PostHog
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

        # Add system info
        event_properties.update(get_system_info())

        # Send event to PostHog
        posthog_client.capture(distinct_id=INSTALLATION_ID, event=event_name, properties=event_properties)
    except Exception as e:
        logger.debug(f"Telemetry error: {e}")


def track_usage(method_name: str | None = None) -> Callable[[F], F]:
    """Decorator to track usage of a method."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Capture event before function execution
            event_name = method_name if method_name is not None else f"{func.__module__}.{func.__name__}"
            capture_event(f"method.called.{event_name}")

            # Execute the function
            result = func(*args, **kwargs)

            # Return the original result
            return result

        return wrapper  # type: ignore

    return decorator
