"""
Cache directory management for Notte.

Provides centralized cache directory handling with fallback to temp directory
when home directory is not writable.
"""

import getpass
import os
import platform
import tempfile
import threading
from enum import Enum
from pathlib import Path

from notte_core.common.logging import logger


class CacheDirectory(str, Enum):
    """Subdirectories within the Notte cache."""

    TELEMETRY = "telemetry"
    TRACES = "traces"
    PROFILING = "profiling"
    FILES = "files"


# Global cache to avoid repeated filesystem checks
_cache_root: Path | None = None
_using_temp_fallback: bool = False
_cache_lock = threading.Lock()  # Thread-safe access to global state


def _get_username() -> str:
    """Get the current username for temp directory isolation.

    Uses getpass.getuser() which tries multiple methods including:
    - Environment variables (LOGNAME, USER, LNAME, USERNAME)
    - pwd.getpwuid() on Unix systems
    - win32api on Windows

    Fallback to "unknown" only as last resort if all methods fail.
    """
    try:
        return getpass.getuser()
    except Exception:
        # Last resort fallback - should rarely happen
        # Even in this case, we try environment variables first
        return os.getenv("USER") or os.getenv("USERNAME") or "unknown"


def _is_writable(path: Path) -> bool:
    """Test if a directory path is writable."""
    try:
        # Try to create the directory if it doesn't exist
        path.mkdir(parents=True, exist_ok=True)

        # Test write permissions with a temporary file
        test_file = path / ".notte_write_test"
        _ = test_file.write_text("test")
        test_file.unlink()
        return True
    except (OSError, PermissionError):
        return False


def get_cache_root(force_recheck: bool = False) -> Path:
    """
    Get the root cache directory for Notte.

    Tries to create ~/.notte/.cache/ first, falls back to temp directory if not writable.
    The result is cached to avoid repeated filesystem checks.

    This function is thread-safe and can be called concurrently from multiple threads.

    Args:
        force_recheck: Force re-checking cache location even if already determined

    Returns:
        Path to the root cache directory
    """
    global _cache_root, _using_temp_fallback

    # Thread-safe access to global cache state
    with _cache_lock:
        # Return cached result if available
        if _cache_root is not None and not force_recheck:
            return _cache_root

        # Try home directory first
        home_cache = Path.home() / ".notte" / ".cache"

        if _is_writable(home_cache):
            _cache_root = home_cache
            _using_temp_fallback = False
            logger.debug(f"Using cache directory: {_cache_root}")
            return _cache_root

        # Fallback to temp directory with user isolation
        username = _get_username()
        temp_cache = Path(tempfile.gettempdir()) / ".notte" / ".cache" / f"{username}"

        try:
            # Create with restricted permissions (owner only)
            temp_cache.mkdir(parents=True, exist_ok=True, mode=0o700)
            _cache_root = temp_cache
            _using_temp_fallback = True
            logger.warning(
                (
                    f"Home directory not writable, using temp cache: {_cache_root}. "
                    "Note: This cache may be cleared by the system."
                )
            )
            return _cache_root
        except (OSError, PermissionError) as e:
            # Last resort - use temp directory without creating subdirectory
            fallback = Path(tempfile.gettempdir()) / ".notte-cache-fallback"
            fallback.mkdir(parents=True, exist_ok=True, mode=0o700)
            _cache_root = fallback
            _using_temp_fallback = True
            logger.error(f"Could not create user-isolated cache directory: {e}. Using fallback: {_cache_root}")
            return _cache_root


def ensure_cache_directory(subdir: CacheDirectory | str | None = None) -> Path:
    """
    Ensure a cache directory exists and return its path.

    Creates the directory if it doesn't exist. If a subdirectory name is provided,
    creates it under the cache root.

    Args:
        subdir: Optional subdirectory name (e.g., "telemetry", "traces")

    Returns:
        Path to the cache directory or subdirectory

    Examples:
        >>> ensure_cache_directory()  # Returns ~/.notte/.cache/
        >>> ensure_cache_directory(CacheDirectory.TELEMETRY)  # Returns ~/.notte/.cache/telemetry/
        >>> ensure_cache_directory("traces")  # Returns ~/.notte/.cache/traces/
    """
    root = get_cache_root()

    if subdir is None:
        return root

    # Convert enum to string if needed
    subdir_name = subdir.value if isinstance(subdir, CacheDirectory) else subdir
    cache_path = root / subdir_name

    try:
        cache_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured cache directory: {cache_path}")
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to create cache subdirectory {cache_path}: {e}")
        raise

    return cache_path


def get_cache_info() -> dict[str, str | bool]:
    """
    Get information about the current cache configuration.

    Returns:
        Dictionary with cache location and status information
    """
    root = get_cache_root()
    return {
        "cache_root": str(root),
        "using_temp_fallback": _using_temp_fallback,
        "platform": platform.system(),
    }


def get_legacy_cache_locations() -> dict[str, Path]:
    """
    Get the old cache locations for migration detection.

    Returns:
        Dictionary mapping cache type to its old location
    """
    system = platform.system()

    # Old telemetry locations
    if system == "Windows":
        appdata = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        telemetry_old = Path(appdata) / "notte" if appdata else Path.home() / "AppData" / "Local" / "notte"
    elif system == "Darwin":
        telemetry_old = Path.home() / "Library" / "Caches" / "notte"
    else:
        telemetry_old = Path.home() / ".cache" / "notte"

    return {
        "telemetry": telemetry_old,
        "files": Path.home() / ".notte.cache",
    }


def check_for_legacy_data() -> dict[str, bool]:
    """
    Check if legacy cache directories exist.

    Returns:
        Dictionary mapping cache type to whether old data exists
    """
    legacy_locations = get_legacy_cache_locations()
    return {cache_type: location.exists() for cache_type, location in legacy_locations.items()}
