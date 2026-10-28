"""Retain failed attempts for three measured live-test flakes, without changing retries.

Session contexts can close before assertions fail, so buffer state at exit and save it
when pytest reports a failure. Persist in-context errors before diagnostic I/O. Never
serialize session responses, cookies, screenshots, page HTML, input values, or history.
DOM diagnostics contain structure/selectors only.
"""

import asyncio
import hashlib
import json
import os
import re
import tempfile
import traceback
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from types import TracebackType
from typing import ParamSpec, TypeVar
from urllib.parse import urlsplit

import pytest
from notte_browser.errors import NoSnapshotObservedError
from notte_browser.session import NotteSession
from notte_core.snapshot import SnapshotMetadata
from notte_core.types import ObserveRequest
from notte_sdk._generated import endpoints as page_api
from notte_sdk.endpoints.sessions import RemoteSession
from patchright.async_api import Request, Response
from pydantic import JsonValue

TARGETS = {
    "tests/integration/sdk/test_scraping.py::test_sdk_scraping_markdown",
    "tests/integration/test_resolution.py::test_action_node_resolution_pipe[news.google.com]",
    "tests/integration/test_special_actions.py::test_evaluate_js_action",
}
ARTIFACT_PATH = Path(".test-artifacts/flake-diagnostics")
_STATE = pytest.StashKey["Diagnostics"]()
_PUBLIC_HOSTS = {"www.notte.cc", "notte.cc", "news.google.com", "consent.google.com", "example.com"}
_LOCAL_CAPTURE_TIMEOUT_SECONDS = 5.0
_DOM_STRUCTURE = """() => {
    const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_ELEMENT);
    const nodes = [];
    const positions = new Map();
    let element = walker.currentNode;
    while (element && nodes.length < 500) {
        nodes.push({tag: element.tagName, parent: positions.get(element.parentElement) ?? null});
        positions.set(element, nodes.length - 1);
        element = walker.nextNode();
    }
    return JSON.stringify({nodes, truncated: element !== null});
}"""
_REMOTE_CAPTURE_TIMEOUT_SECONDS = 5.0
_P = ParamSpec("_P")
_R = TypeVar("_R")


def redact(text: str) -> str:
    # Resolve at write time: the selected tests load dotenv after fixture setup.
    for name, value in sorted(os.environ.items(), key=lambda pair: len(pair[1]), reverse=True):
        if value and re.search(r"KEY|TOKEN|PASSWORD|SECRET|AUTH|EMAIL", name, re.I):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"(?im)\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*[:=][^\n]*", "[REDACTED]", text)
    text = re.sub(r"(?i)\bBearer\s+[^\s'\"<>]+", "Bearer [REDACTED]", text)
    text = re.sub(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\b[\"']?\s*[:=]\s*[^\s,;<>]+",
        "[REDACTED]",
        text,
    )

    def origin(match: re.Match[str]) -> str:
        try:
            url = urlsplit(match[0])
            return f"{url.scheme}://{url.hostname or '[REDACTED]'}"
        except ValueError:
            return "[REDACTED URL]"

    # Paths, query strings, fragments and URL credentials are unnecessary here.
    return re.sub(r"(?:https?|wss?)://[^\s<>\"']+", origin, text, flags=re.I)


def metadata_text(metadata: SnapshotMetadata) -> str:
    return json.dumps(
        {
            "url": metadata.url,
            "title": metadata.title,
            "timestamp": metadata.timestamp.isoformat(),
            "viewport": metadata.viewport.model_dump(),
        },
        indent=2,
    )


def redact_json(value: JsonValue) -> JsonValue:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_json(entry) for entry in value]
    if isinstance(value, dict):
        return {redact(key): redact_json(entry) for key, entry in value.items()}
    return value


@dataclass
class Diagnostics:
    files: dict[str, str] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    directories: dict[str, Path] = field(default_factory=dict)
    scrape_result_invalid: bool = False

    def record(self, name: str, capture: Callable[[], str]) -> None:
        try:
            text = capture()
            if len(text) > 64_000:
                # Redact whole values before truncation can leave an unrecognizable secret prefix.
                text = json.dumps(redact_json(json.loads(text))) if name.endswith(".json") else redact(text)
                text = json.dumps({"truncated": True, "preview": text[:64_000]})
            self.files[name] = text
        except Exception:
            self.files[f"{name}.capture-error.txt"] = traceback.format_exc()

    def before_exit(self, error: BaseException | None, item: pytest.Item | None = None) -> None:
        if error is not None:
            self.files["before-cleanup-error.txt"] = "".join(traceback.format_exception(error))
            if item is not None:
                try:
                    self.write(item, "call", self.files)
                except Exception:
                    self.files["write.capture-error.txt"] = traceback.format_exc()

    def write(self, item: pytest.Item, phase: str, files: dict[str, str]) -> Path:
        if phase not in self.directories:
            root = item.config.rootpath / ARTIFACT_PATH / hashlib.sha256(item.nodeid.encode()).hexdigest()[:16]
            root.mkdir(parents=True, exist_ok=True)
            attempt = getattr(item, "execution_count", 1)
            self.directories[phase] = Path(tempfile.mkdtemp(prefix=f"attempt-{attempt}-{phase}-", dir=root))
        directory = self.directories[phase]
        for name, text in files.items():
            text = json.dumps(redact_json(json.loads(text)), indent=2) if name.endswith(".json") else redact(text)
            _ = (directory / name).write_text(text, encoding="utf-8")
        return directory

    def event(self, text: str) -> None:
        if len(self.events) < 30:
            self.events.append(text)

    def request_failed(self, request: Request) -> None:
        self.event(f"requestfailed {request.method} {request.url}: {request.failure}")

    def response(self, response: Response) -> None:
        if response.status >= 400:
            self.event(f"response {response.status} {response.url}")

    async def local(self, session: NotteSession, *, capture_live: bool = True) -> None:
        self.record(
            "session.json",
            lambda: json.dumps(
                {"kind": "local", "session_id": None, "page_closed": session.page.is_closed(), "url": session.page.url}
            ),
        )
        observation = session.trajectory.last_observation
        if observation is not None:
            self.record("observation.json", lambda: metadata_text(observation.metadata))
        result = session.trajectory.last_result
        if result is not None:
            self.record("result.json", lambda: json.dumps({"success": result.success, "message": result.message}))

        try:
            snapshot = session.snapshot
        except NoSnapshotObservedError:
            if not capture_live:
                return
            # Action-only tests have no observation cache. Read once, without invoking
            # another browser action or changing the session's snapshot/trajectory.
            if urlsplit(session.page.url).hostname not in _PUBLIC_HOSTS:
                self.files["nodes.json"] = json.dumps({"omitted": "page is outside the public test hosts"})
                return
            try:
                # The normal snapshot builder retries DOM evaluation. These two
                # read-only calls share one diagnostic budget and never retry.
                async with asyncio.timeout(_LOCAL_CAPTURE_TIMEOUT_SECONDS):
                    metadata = await session.window.snapshot_metadata()
                    self.record("observation.json", lambda: metadata_text(metadata))
                    if urlsplit(metadata.url).hostname not in _PUBLIC_HOSTS:
                        self.files["nodes.json"] = json.dumps({"omitted": "page is outside the public test hosts"})
                    else:
                        structure = await session.page.evaluate(_DOM_STRUCTURE)
                        self.record("nodes.json", lambda: structure)
            except Exception:
                self.files["snapshot.capture-error.txt"] = traceback.format_exc()
            return

        if observation is None:
            self.record("observation.json", lambda: metadata_text(snapshot.metadata))

        def nodes() -> str:
            if urlsplit(snapshot.metadata.url).hostname not in _PUBLIC_HOSTS:
                return json.dumps({"omitted": "page is outside the public test hosts"})
            return json.dumps(
                [
                    {
                        "id": node.id,
                        "role": node.get_role_str(),
                        "selectors": node.computed_attributes.selectors.model_dump()
                        if node.computed_attributes.selectors is not None
                        else None,
                    }
                    for node in list(snapshot.interaction_nodes())[:500]
                ],
                indent=2,
            )

        self.record("nodes.json", nodes)

    def remote(self, session: RemoteSession, *, capture_observation: bool = True) -> None:
        def status() -> str:
            response = session.response
            return json.dumps(
                {
                    "kind": "remote",
                    "session_id": session.session_id,
                    "status_source": "cached response before cleanup",
                    "status": response.status if response is not None else None,
                    "close_reason": response.close_reason if response is not None else None,
                    "error": response.error if response is not None else None,
                }
            )

        # Keep the ID even if the status/observation request itself fails.
        self.record("session-id.txt", lambda: session.session_id)
        self.record("session.json", status)
        if not capture_observation:
            return

        def observation() -> str:
            observed = session.client.page.request(
                page_api.page_observe(session.session_id, ObserveRequest(perception_type="fast")),
                timeout=_REMOTE_CAPTURE_TIMEOUT_SECONDS,
            )
            if urlsplit(observed.metadata.url).hostname not in _PUBLIC_HOSTS:
                return "Observation omitted: page is outside the public test hosts."
            # Only selector structure, never element_states or field values.
            return (
                metadata_text(observed.metadata)
                + "\n"
                + json.dumps(
                    [
                        {"id": action.id, "type": action.type, "selector": action.selector.playwright_selector}
                        for action in list(observed.space.interaction_actions)[:500]
                    ],
                    indent=2,
                )
            )

        # Diagnostic reads must not add transport retries to the test's existing policy.
        client = session.client.root_client
        retries = client.max_retries
        try:
            client.max_retries = 0
            self.record("observation.txt", observation)
        finally:
            client.max_retries = retries


@pytest.fixture(autouse=True)
def retain_flake_diagnostics(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.nodeid not in TARGETS:
        yield
        return
    state = Diagnostics()
    request.node.stash[_STATE] = state
    monkeypatch = request.getfixturevalue("monkeypatch")
    local_start = NotteSession.astart
    local_exit = NotteSession.__aexit__
    remote_exit = RemoteSession.__exit__
    remote_scrape = RemoteSession.scrape

    def track_scrape_result(scrape: Callable[_P, _R]) -> Callable[_P, _R]:
        @wraps(scrape)
        def tracked(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            result = scrape(*args, **kwargs)
            # The selected SDK test asserts these after client.scrape has closed
            # its session. Preserve its exact result and capture before cleanup.
            try:
                state.scrape_result_invalid = not isinstance(result, str) or len(result) == 0
            except Exception:
                state.files["scrape-result.capture-error.txt"] = traceback.format_exc()
            return result

        return tracked

    async def start(session: NotteSession) -> None:
        await local_start(session)
        try:
            session.page.on("pageerror", lambda error: state.event(f"pageerror {error}"))
            session.page.on("requestfailed", state.request_failed)
            session.page.on("response", state.response)
        except Exception:
            state.files["listeners.capture-error.txt"] = traceback.format_exc()
        except BaseException as error:
            # Context entry has not completed, so its caller cannot run __aexit__.
            await local_exit(session, type(error), error, error.__traceback__)
            raise

    async def exit_local(
        session: NotteSession,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            state.before_exit(exc_val, request.node)
            await state.local(session, capture_live=exc_val is not None)
        except Exception:
            state.files["local.capture-error.txt"] = traceback.format_exc()
        finally:
            await local_exit(session, exc_type, exc_val, exc_tb)

    def exit_remote(
        session: RemoteSession,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            state.before_exit(exc_val, request.node)
            state.remote(session, capture_observation=exc_val is not None or state.scrape_result_invalid)
        except Exception:
            state.files["remote.capture-error.txt"] = traceback.format_exc()
        finally:
            remote_exit(session, exc_type, exc_val, exc_tb)

    monkeypatch.setattr(NotteSession, "astart", start)
    monkeypatch.setattr(NotteSession, "__aexit__", exit_local)
    monkeypatch.setattr(RemoteSession, "__exit__", exit_remote)
    monkeypatch.setattr(RemoteSession, "scrape", track_scrape_result(remote_scrape))
    yield


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if not report.failed or item.nodeid not in TARGETS:
        return report
    state = item.stash.get(_STATE, Diagnostics())
    try:
        attempt = getattr(item, "execution_count", 1)
        files = {
            "failure.txt": report.longreprtext,
            "test.txt": f"{item.nodeid}\nattempt={attempt}\nphase={report.when}\n",
            "events.txt": "\n".join(state.events),
            **state.files,
        }
        directory = state.write(item, report.when, files)
        report.sections.append(("retained diagnostics", str(directory.relative_to(item.config.rootpath))))
    except Exception:
        report.sections.append(("diagnostics capture failed", redact(traceback.format_exc())))
    return report
