import atexit
import importlib.metadata as metadata
import inspect
import logging
import os
import platform
import threading
import uuid
from collections import deque
from functools import cache, wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from packaging import version

from notte_core.cache import CacheDirectory, ensure_cache_directory

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


# Telemetry does no file or network I/O at import time: the cache directory, the clients and the
# installation id are created on the first captured event.
@cache
def _telemetry_paths() -> tuple[Path, Path, Path]:
    telemetry_dir = _get_telemetry_dir()
    return telemetry_dir, telemetry_dir / "telemetry_user_id", telemetry_dir / "download_version"


POSTHOG_API_KEY: str = "phc_6U4lU1RMI2hyj9DREkuyPFFDg95b0LYkoeaZ0LfaeVb"  # pragma: allowlist secret
POSTHOG_HOST: str = "https://us.i.posthog.com"
SCARF_GATEWAY_URL = "https://scarf.notte.cc/events"

F = TypeVar("F", bound=Callable[..., Any])

DEBUG_LOGGING = os.environ.get("NOTTE_LOGGING_LEVEL", "info").lower() == "debug"

POSTHOG_EVENT_SETTINGS = {
    "process_person_profile": True,
}


def setup_posthog() -> Any | None:
    """Set up the PostHog client if enabled."""
    if DISABLE_TELEMETRY:
        return None

    try:
        import posthog

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
        from scarf.event_logger import ScarfEventLogger  # pyright: ignore[reportMissingTypeStubs]

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


def track_package_download(
    scarf_client: Any | None, installation_id: str, properties: dict[str, Any] | None = None
) -> None:
    """Track package download event specifically for Scarf analytics"""
    if DISABLE_TELEMETRY:
        return None
    _, _, version_download_path = _telemetry_paths()

    if scarf_client is not None:
        try:
            current_version = __version__
            should_track = False
            first_download = False

            # Check if version file exists
            if not os.path.exists(version_download_path):
                # First download
                should_track = True
                first_download = True

                # Save version (directory already created by ensure_cache_directory)
                with open(version_download_path, "w") as f:
                    _ = f.write(current_version)
            else:
                # Read saved version
                with open(version_download_path) as f:
                    saved_version = f.read().strip()

                # Compare versions (simple string comparison for now)
                if version.parse(current_version) > version.parse(saved_version):
                    should_track = True
                    first_download = False

                    # Update saved version
                    with open(version_download_path, "w") as f:
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


def get_or_create_installation_id(scarf_client: Any | None = None) -> str:
    """Get existing installation ID or create and save a new one."""
    if DISABLE_TELEMETRY:
        return ""

    _, user_id_path, _ = _telemetry_paths()
    if user_id_path.exists():
        return user_id_path.read_text().strip()

    installation_id = str(uuid.uuid4())
    # The telemetry directory is already created by ensure_cache_directory
    _ = user_id_path.write_text(installation_id)  # Assign to _ to acknowledge unused result

    # Always check for version-based download tracking
    track_package_download(
        scarf_client,
        installation_id,
        {
            "triggered_by": "user_id_property",
        },
    )
    return installation_id


@cache
def _clients() -> tuple[Any | None, Any | None, str]:
    """PostHog client, Scarf client and installation id, created on first use."""
    posthog_client = setup_posthog()
    # Covers events captured by non-daemon threads after the `threading` exit hook ran. Registered after
    # PostHog's client, so it runs before PostHog's own exit flush, which then sends what it was handed.
    _ = atexit.register(_flush_at_exit)
    scarf_client = setup_scarf()
    return posthog_client, scarf_client, get_or_create_installation_id(scarf_client)


def get_system_info() -> dict[str, Any]:
    """Get anonymous system information."""
    if DISABLE_TELEMETRY:
        return {}

    return {
        "os": platform.system(),
        "python_version": platform.python_version(),
        "notte_version": __version__,
    }


MAX_QUEUED_EVENTS = 1000
EXIT_FLUSH_TIMEOUT_SECONDS = 1.0
FORK_WAIT_SECONDS = 2.0


class _EventQueue:
    """Sends events from one background thread so telemetry never blocks the caller.

    The queue keeps the newest `max_events` events and drops the oldest when full.
    """

    def __init__(self, max_events: int) -> None:
        self.max_events: int = max_events
        self.reset()

    def reset(self) -> None:
        self._condition: threading.Condition = threading.Condition()
        self._events: deque[tuple[str, dict[str, Any]]] = deque(maxlen=self.max_events)
        self._sending: bool = False
        self._worker: threading.Thread | None = None
        self._first_send_done: threading.Event = threading.Event()

    def put(self, event_name: str, properties: dict[str, Any]) -> None:
        with self._condition:
            if len(self._events) == self.max_events:
                logger.debug("Telemetry queue is full, dropping the oldest event")
            self._events.append((event_name, properties))
            if self._worker is None:
                worker = threading.Thread(target=self._run, name="notte-telemetry", daemon=True)
                worker.start()
                self._worker = worker
            self._condition.notify()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._events:
                    _ = self._condition.wait()
                event_name, properties = self._events.popleft()
                self._sending = True
            try:
                _send_event(event_name, properties)
            except Exception as e:
                logger.debug(f"Failed to send telemetry event {event_name}: {e}")
            finally:
                self._first_send_done.set()
                with self._condition:
                    self._sending = False
                    self._condition.notify_all()

    def flush(self, timeout: float) -> bool:
        """Wait up to `timeout` seconds for queued events to be sent. Returns whether the queue drained."""
        with self._condition:
            return self._condition.wait_for(lambda: not self._events and not self._sending, timeout)

    def wait_for_first_send(self, timeout: float) -> None:
        if self._worker is not None:
            _ = self._first_send_done.wait(timeout)


_event_queue = _EventQueue(MAX_QUEUED_EVENTS)
_exit_flush_registered = False
_exit_flush_timed_out = False


def _flush_at_exit() -> None:
    global _exit_flush_timed_out
    # Runs from two exit hooks; once the endpoint has failed to keep up, the second does not wait again.
    if _exit_flush_timed_out:
        return
    _exit_flush_timed_out = not _event_queue.flush(EXIT_FLUSH_TIMEOUT_SECONDS)


def _register_exit_flush() -> None:
    global _exit_flush_registered
    if _exit_flush_registered:
        return
    # `threading._register_atexit` (also used by `concurrent.futures`) runs before `atexit` handlers, so
    # PostHog's own exit flush still delivers what we hand it, and it also runs when a multiprocessing child
    # started with `fork` exits, which skips `atexit`.
    try:
        threading._register_atexit(_flush_at_exit)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    except RuntimeError:
        return  # shutdown has started; the `atexit` flush registered in `_clients` still runs
    _exit_flush_registered = True


def _wait_before_fork() -> None:
    # The first send imports modules lazily (the PostHog and Scarf clients, PostHog's platform lookup,
    # requests' proxy handling). Forking while the worker holds an import lock leaves that module locked
    # forever in the child, so a fork waits (bounded) for the first send; later sends reuse those modules.
    _event_queue.wait_for_first_send(FORK_WAIT_SECONDS)


def _reset_after_fork() -> None:
    # The parent sends its own queued events. The child starts with an empty queue and new clients,
    # since the parent's worker thread does not exist in the child and Scarf's HTTP connection is shared.
    _event_queue.reset()
    _clients.cache_clear()


if hasattr(os, "register_at_fork"):  # not available on Windows
    os.register_at_fork(before=_wait_before_fork, after_in_child=_reset_after_fork)


def flush(timeout: float = EXIT_FLUSH_TIMEOUT_SECONDS) -> bool:
    """Wait up to `timeout` seconds for captured events to be sent. Returns whether all were sent."""
    return _event_queue.flush(timeout)


def capture_event(event_name: str, properties: dict[str, Any] | None = None) -> None:
    """Capture an event if telemetry is enabled. Events are sent in the background."""
    if DISABLE_TELEMETRY:
        return None
    try:
        _register_exit_flush()
        _event_queue.put(event_name, dict(properties or {}))
    except Exception as e:
        logger.debug(f"Failed to queue telemetry event {event_name}: {e}")


def _send_event(event_name: str, properties: dict[str, Any]) -> None:
    try:
        posthog_client, scarf_client, installation_id = _clients()
    except Exception as e:
        logger.debug(f"Failed to initialize telemetry: {e}")
        return None
    # send to posthog
    if posthog_client is not None:
        try:
            # Each destination gets its own copy: never mutate the caller's dict or leak keys across.
            event_properties = dict(properties or {})
            event_properties.update(get_system_info())
            event_properties.update(POSTHOG_EVENT_SETTINGS)

            if DEBUG_LOGGING:
                logger.debug(f"Telemetry event: {event_name} {event_properties}")

            posthog_client.capture(distinct_id=installation_id, event=event_name, properties=event_properties)
        except Exception as e:
            logger.debug(f"Failed to send telemetry event {event_name}: {e}")
    # send to scarf
    if scarf_client is not None:
        try:
            # Add package version and user_id to all events
            scarf_properties = dict(properties or {})
            scarf_properties.update(get_system_info())
            scarf_properties["event"] = event_name
            scarf_properties["installation_id"] = installation_id
            scarf_client.log_event(properties=scarf_properties)
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
