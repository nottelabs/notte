# pyright: basic
"""What a benchmark task and a probe are, and the helpers their success checks share.

A task's `check` runs on the final page probe (`runners.PROBE_JS`: URL, text, inputs, tables, ...) and the run
record (steps, decisions), never on the runner's own claim.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

MAX_STEPS = 15
REAL_MAX_STEPS = 25  # real sites need more steps
# `{fixtures}` in a URL is replaced by the base URL of the local fixture server (`fixtures/`)
FIXTURES = "{fixtures}"
# operations that leave the page as it is: allowed in the tasks that must not act
NEUTRAL_OPERATIONS = ("SCROLL_DOWN", "SCROLL_UP", "WAIT")

Check = Callable[[dict[str, Any], dict[str, Any]], bool]


@dataclass(frozen=True)
class Task:
    name: str
    url: str
    goal: str
    # (final page probe, run record) -> success
    check: Check
    tags: tuple[str, ...] = field(default=())
    max_steps: int = MAX_STEPS
    # JS evaluated right after the first navigation, saved as `run["pre"]` (e.g. the expected target)
    pre_js: str | None = None
    # selection label (`--suites`); empty: the name of the module in `tasks/` that defines the task
    suite: str = ""

    @property
    def fixture(self) -> bool:
        """On the local fixture server: no site noise, so it must always pass (see `rules.py`)."""
        return self.url.startswith(FIXTURES)


@dataclass(frozen=True)
class Probe:
    name: str
    url: str
    question: str
    # choose(): the options; check(): None
    options: list[str] | None
    # choose(): the right option; check(): "YES" / "NO"
    answer: str
    suite: str = ""

    @property
    def fixture(self) -> bool:
        return self.url.startswith(FIXTURES)


def qs(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def one(url: str, key: str) -> str | None:
    values = qs(url).get(key)
    return values[0] if values else None


def path(final: dict[str, Any]) -> str:
    return urlsplit(final["url"]).path


def query_ok(page: str, **expected: str) -> Check:
    """The final page is `page` with these query parameters (a fixture form submitted with GET)."""

    def check(final: dict[str, Any], _: dict[str, Any]) -> bool:
        return path(final).endswith(page) and all(one(final["url"], k) == v for k, v in expected.items())

    return check


def executed(run: dict[str, Any]) -> list[str]:
    return [s.get("operation") or "" for s in run.get("steps", []) if s.get("status") == "executed"]


def last_status(run: dict[str, Any]) -> str | None:
    steps = run.get("steps") or []
    return steps[-1].get("status") if steps else None


def visited(run: dict[str, Any]) -> list[str]:
    """URLs of the pages the decider was shown, in order (from the recorded decision states)."""
    return [s["url"] for s in run.get("steps", []) if s.get("url")]


def checkboxes(final: dict[str, Any]) -> list[bool]:
    return [i["checked"] for i in final.get("inputs") or [] if i["type"] == "checkbox"]


def frame_value(final: dict[str, Any], input_id: str) -> str | None:
    for frame in final.get("frames") or []:
        for i in frame.get("inputs") or []:
            if i["id"] == input_id:
                return i["value"]
    return None
