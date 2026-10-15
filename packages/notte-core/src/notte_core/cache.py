"""
Cache directory management for Notte.

Provides centralized cache directory handling with fallback to temp directory
when home directory is not writable.
"""

import getpass
import os
import tempfile
import threading
from enum import Enum
from pathlib import Path

from notte_core.logging import logger


class CacheDirectory(str, Enum):
    """Subdirectories within the Notte cache."""

    TELEMETRY = "telemetry"
    TRACES = "traces"
    PROFILING = "profiling"
    FILES = "files"


# Global cache to avoid repeated filesystem checks
_cache_root: Path | None = None
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
    global _cache_root

    # Thread-safe access to global cache state
    with _cache_lock:
        # Return cached result if available
        if _cache_root is not None and not force_recheck:
            return _cache_root

        # Try home directory first
        home_cache = Path.home() / ".notte" / ".cache"

        if _is_writable(home_cache):
            _cache_root = home_cache
            logger.debug(f"Using cache directory: {_cache_root}")
            return _cache_root

        # Fallback to temp directory with user isolation
        username = _get_username()
        temp_cache = Path(tempfile.gettempdir()) / ".notte" / ".cache" / f"{username}"

        try:
            # Create with restricted permissions (owner only)
            temp_cache.mkdir(parents=True, exist_ok=True, mode=0o700)
            _cache_root = temp_cache
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
