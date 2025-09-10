import getpass
import json
import re
import sys
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any, final

from loguru import logger
from notte_core.actions import FormFillAction

from notte_sdk.endpoints.sessions import RemoteSession


@final
class LogCapture:
    """
    Simple log capture context manager that captures stdout/stderr and extracts session IDs.

    Usage:
        with LogCapture() as log_capture:
            print("This will be captured")

        session_id = log_capture.session_id
        all_logs = log_capture.get_all_logs()
    """

    def __init__(self, passthrough: bool = True, write_callback: Callable[[str], None] | None = None):
        """
        Initialize the log capture.

        Args:
            passthrough: Whether to also write to original streams (default: True)
        """
        self.write_callback: Callable[[str], None] | None = write_callback
        self.session_id: str | None = None
        self.buffer = StringIO()
        self.passthrough = passthrough
        self.all_logs: list[str] = []

        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

    def __enter__(self) -> "LogCapture":
        """Start capturing logs."""
        sys.stdout = self
        sys.stderr = self
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop capturing and restore original streams."""
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

    def write(self, message: Any) -> int:
        """Capture written messages."""
        message_str = str(message)

        if self.write_callback is not None:
            try:
                self.write_callback(message_str)
            except Exception as e:
                logger.error(f"Exception while writing {e}")

        # Store the message
        written = self.buffer.write(message_str)
        self.all_logs.append(message_str)

        # Extract session ID if we haven't found one yet
        if not self.session_id:
            match = re.search(
                r"\[Session\] ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}) started with request:",
                message_str,
            )
            if match:
                self.session_id = match.group(1)

        # Pass through to original if enabled
        if self.passthrough:
            try:
                _ = self.original_stdout.write(message_str)
                _ = self.original_stdout.flush()
            except Exception:
                pass  # Ignore errors (e.g., Lambda environment)

        return written

    def flush(self) -> None:
        """Flush the buffer."""
        if self.passthrough:
            try:
                _ = self.original_stdout.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        """Return False as we're not a TTY."""
        return False

    def get_logs(self) -> list[str]:
        """Return all captured logs as a single string."""
        return self.all_logs


def generate_cookies(session: RemoteSession, url: str, output_path: str) -> None:
    if not output_path.endswith(".json"):
        raise ValueError(f"Output path must end with .json: {output_path}")

    _ = session.execute(dict(type="goto", url=url))

    email = input("Enter your email: ")
    password = getpass.getpass(prompt="Enter your password: ")

    form_fill_action = FormFillAction(value=dict(email=email, current_password=password))  # type: ignore

    res = session.execute(form_fill_action)
    if not res.success:
        logger.error(f"Failed to fill email & password: {res.message}")
        raise ValueError("Failed to fill email & password")
    logger.info("✅ Successfully filled email & password")

    obs = session.observe(instructions="Click on the 'Sign in' button", perception_type="deep")
    signin = obs.space.first()
    res = session.execute(signin)
    if not res.success:
        logger.error(f"Failed to click on the 'Sign in' button: {res.message}")
        return
    logger.info("✅ Successfully clicked on the 'Sign in' button")

    logger.info("Waiting for 5 seconds to let the page load...")
    _ = session.execute(dict(type="wait", time_ms=5000))
    # save cookies
    cookies = session.get_cookies()

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(cookies, f)

    if len(cookies) == 0:
        logger.error("❌ No cookies created during the login process. Try again or do it manually.")

    logger.info(f"🔥 Successfully saved {len(cookies)} cookies to {output_path}")
