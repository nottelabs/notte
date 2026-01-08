import asyncio
import builtins
import contextlib
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Disable telemetry to ensure no background writes interfere
os.environ["DISABLE_TELEMETRY"] = "true"

from notte_sdk import NotteClient


@contextlib.contextmanager
def readonly_filesystem():
    """
    Context manager that strictly enforces a read-only filesystem.
    It patches builtins.open and os module functions used by pathlib.
    """
    original_open = builtins.open

    # 1. Patch builtins.open (handles open(), Path.write_text, Path.write_bytes, Path.read_text, etc.)
    def mocked_open(file, mode="r", *args, **kwargs):
        if any(c in mode for c in ("w", "a", "x", "+")):
            raise PermissionError(f"Write access denied to '{file}' in read-only mode (mode='{mode}')")
        return original_open(file, mode, *args, **kwargs)

    # 2. Patch low-level os functions (handles Path.mkdir, Path.touch, Path.unlink, etc.)
    def deny_write_op(name):
        def _fail(*args, **kwargs):
            raise PermissionError(f"Filesystem modification denied: os.{name}() called")

        return _fail

    # List of os functions that modify the filesystem
    fs_write_ops = [
        "mkdir",
        "makedirs",
        "remove",
        "unlink",
        "rmdir",
        "removedirs",
        "rename",
        "replace",
        "chmod",
        "chown",
        "symlink",
        "link",
    ]

    patches = [
        patch("builtins.open", side_effect=mocked_open),
        patch("io.open", side_effect=mocked_open),
    ]

    # Add patches for all write operations in os module
    for op in fs_write_ops:
        if hasattr(os, op):
            patches.append(patch(f"os.{op}", side_effect=deny_write_op(op)))

    # Apply all patches
    for p in patches:
        p.start()

    try:
        yield
    finally:
        for p in patches:
            p.stop()


def test_download_file_action_is_strictly_readonly():
    """
    Verifies that session execution (including download_file) does not perform
    ANY write operations (mkdir, touch, write) to the local disk.
    """
    # Initialize client (reading config/env is allowed)
    client = NotteClient()
    storage = client.FileStorage()

    # Enter the strict read-only context
    with readonly_filesystem():
        try:
            # ----------------------------------------------------------------
            # 1. Verify the harness works by intentionally trying to write
            # ----------------------------------------------------------------

            test_path = Path("test_blocked.txt")

            # Test 1: pathlib.write_text (caught by open)
            with pytest.raises(PermissionError, match="Write access denied"):
                test_path.write_text("should fail")

            # Test 2: pathlib.mkdir (caught by os.mkdir)
            with pytest.raises(PermissionError, match="Filesystem modification denied"):
                Path("should_fail_dir").mkdir()

            # ----------------------------------------------------------------
            # 2. Run the actual User Scenario
            # ----------------------------------------------------------------

            # Mock the session start and execute methods to avoid network calls
            with client.Session(storage=storage, open_viewer=False) as session:
                _ = session.execute(type="goto", url="https://arxiv.org/abs/1706.03762")
                _ = session.execute(type="click", selector='internal:role=link[name="View PDF"i]')
                time.sleep(5)  # reduced sleep for test speed

                # This action triggers a remote download.
                # If it attempts to create a local folder or save the file, this will FAIL.
                session.execute(type="download_file", selector="body")

            # Verify that accessing the file locally triggers a permission error
            # This can trigger either "Filesystem modification denied" (mkdir) or "Write access denied" (open)
            with pytest.raises(PermissionError, match="Filesystem modification denied|Write access denied"):
                files = storage.list_downloaded_files()
                _ = asyncio.run(storage.get_file(files[0]))

        except PermissionError as e:
            pytest.fail(f"Read-only violation detected: {e}")
        except Exception as e:
            # Catch other potential errors (like network issues) unrelated to fs permissions
            if "Filesystem modification denied" in str(e):
                pytest.fail(f"Read-only violation detected: {e}")
            raise e
