"""The User-Agent the SDK sends to the Notte API.

It names the SDK, its version and the Python runtime, and inside GitHub Actions
the repository, run and job that run it, so failing sessions can be traced back
to the CI job that started them. It is only sent to the Notte API.
"""

import os
import platform
import re
import sys

from notte_core import __version__ as notte_core_version

_UNSAFE = re.compile(r"[^A-Za-z0-9._/-]")
_MAX_VALUE_LENGTH = 100


def _value(name: str) -> str | None:
    raw = os.getenv(name)
    if not raw:
        return None
    return _UNSAFE.sub("_", raw)[:_MAX_VALUE_LENGTH]


def github_actions_context() -> str | None:
    """``github-actions (repo=...; run=...; job=...)`` inside a GitHub Actions job, otherwise None."""
    if os.getenv("GITHUB_ACTIONS") != "true":
        return None
    run, attempt = _value("GITHUB_RUN_ID"), _value("GITHUB_RUN_ATTEMPT")
    fields = [
        ("repo", _value("GITHUB_REPOSITORY")),
        ("run", f"{run}/{attempt}" if run and attempt else run),
        ("job", _value("GITHUB_JOB")),
    ]
    return "github-actions (" + "; ".join(f"{key}={value}" for key, value in fields if value) + ")"


def client_user_agent() -> str:
    """The SDK's User-Agent, read from the environment on each call."""
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    agent = f"notte-sdk-python/{notte_core_version} (python {python}; {platform.system().lower()})"
    ci = github_actions_context()
    return agent if ci is None else f"{agent} {ci}"
