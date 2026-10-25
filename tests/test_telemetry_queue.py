import gzip
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from notte_core import telemetry


def enable_telemetry(monkeypatch: pytest.MonkeyPatch, max_events: int = telemetry.MAX_QUEUED_EVENTS) -> None:
    """Send this test's events through a fresh queue."""
    queue = telemetry._EventQueue(max_events)
    monkeypatch.setattr(telemetry, "_event_queue", queue)
    monkeypatch.setattr(telemetry, "DISABLE_TELEMETRY", False)
    monkeypatch.setattr(telemetry, "get_system_info", lambda: {})


class BlockingScarf:
    """Records events; each send waits until `release` is set."""

    def __init__(self) -> None:
        self.release: threading.Event = threading.Event()
        self.started: threading.Event = threading.Event()
        self.events: list[str] = []

    def log_event(self, *, properties: dict[str, Any]) -> None:
        self.started.set()
        _ = self.release.wait(timeout=10)
        self.events.append(properties["event"])


@pytest.mark.asyncio
async def test_tracked_calls_do_not_wait_for_a_slow_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    enable_telemetry(monkeypatch)
    scarf = BlockingScarf()
    monkeypatch.setattr(telemetry, "_clients", lambda: (None, scarf, "installation"))

    @telemetry.track_usage("test.sync")
    def sync_call() -> str:
        return "sync"

    @telemetry.track_usage("test.async")
    async def async_call() -> str:
        return "async"

    started = time.perf_counter()
    assert sync_call() == "sync"
    assert await async_call() == "async"
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert scarf.events == []
    scarf.release.set()
    assert telemetry.flush(timeout=5)
    assert scarf.events == ["test.sync", "test.async"]


def test_full_queue_drops_the_oldest_events(monkeypatch: pytest.MonkeyPatch) -> None:
    enable_telemetry(monkeypatch, max_events=3)
    scarf = BlockingScarf()
    monkeypatch.setattr(telemetry, "_clients", lambda: (None, scarf, "installation"))

    telemetry.capture_event("test.0")
    assert scarf.started.wait(timeout=5)
    for index in range(1, 6):
        telemetry.capture_event(f"test.{index}")

    assert not telemetry.flush(timeout=0.05)
    scarf.release.set()
    assert telemetry.flush(timeout=5)
    # test.0 was already being sent; of the five queued after it, the newest three are kept.
    assert scarf.events == ["test.0", "test.3", "test.4", "test.5"]


def test_capture_event_does_not_raise_when_the_worker_cannot_start(monkeypatch: pytest.MonkeyPatch) -> None:
    enable_telemetry(monkeypatch)

    def fail_to_start(self: threading.Thread) -> None:
        raise RuntimeError("can't create new thread at interpreter shutdown")

    monkeypatch.setattr(threading.Thread, "start", fail_to_start)

    telemetry.capture_event("test.event")


@dataclass
class Collector:
    url: str
    release: threading.Event
    requests: list[tuple[str, bytes]] = field(default_factory=list)

    def scarf_events(self) -> list[str]:
        return [json.loads(body)["event"] for path, body in self.requests if path == "/events"]

    def posthog_bodies(self) -> list[bytes]:
        return [body for path, body in self.requests if path != "/events"]


def collector(scarf_delay: float, hang: bool = False) -> Iterator[Collector]:
    release = threading.Event()
    requests: list[tuple[str, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            if hang:
                _ = release.wait(timeout=30)
            elif self.path == "/events":
                time.sleep(scarf_delay)
            requests.append((self.path.split("?")[0], body))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            _ = self.wfile.write(b"{}")

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Collector(url=f"http://127.0.0.1:{server.server_address[1]}", release=release, requests=requests)
    finally:
        release.set()
        server.shutdown()
        server.server_close()


@pytest.fixture
def slow_endpoint() -> Iterator[Collector]:
    yield from collector(scarf_delay=0.05)


@pytest.fixture
def hanging_endpoint() -> Iterator[Collector]:
    yield from collector(scarf_delay=0, hang=True)


def run_script(code: str, endpoint: Collector, tmp_path: Path, *, disable: bool = False) -> float:
    """Run `code` in a fresh interpreter with the real telemetry clients pointed at `endpoint`."""
    prelude = (
        "from notte_core import telemetry\n"
        f"telemetry.SCARF_GATEWAY_URL = {endpoint.url + '/events'!r}\n"
        f"telemetry.POSTHOG_HOST = {endpoint.url!r}\n"
    )
    env = {
        **os.environ,
        "DISABLE_TELEMETRY": "true" if disable else "false",
        "XDG_CACHE_HOME": str(tmp_path),
        # Reach the local endpoint directly. Without this, requests asks macOS for the system proxy,
        # which is not fork-safe and crashes forked children whatever sends the request.
        "NO_PROXY": "127.0.0.1",
    }
    started = time.perf_counter()
    _ = subprocess.run([sys.executable, "-c", prelude + code], check=True, env=env, timeout=60)
    return time.perf_counter() - started


def test_events_are_sent_before_a_short_script_exits(slow_endpoint: Collector, tmp_path: Path) -> None:
    code = "for _ in range(3):\n    telemetry.capture_event('test.exit', {'status': 'success'})\n"

    _ = run_script(code, slow_endpoint, tmp_path)

    assert slow_endpoint.scarf_events().count("test.exit") == 3
    # PostHog's own exit flush runs after ours, so it still sends what the worker handed it.
    assert sum(body.count(b'"test.exit"') for body in slow_endpoint.posthog_bodies()) == 3


def test_events_from_threads_still_running_at_exit_are_sent(slow_endpoint: Collector, tmp_path: Path) -> None:
    # The `threading` exit hook runs before Python waits for non-daemon threads, so the late event is sent
    # by the `atexit` flush.
    code = (
        "import threading, time\n"
        "def late():\n"
        "    time.sleep(0.5)\n"
        "    telemetry.capture_event('test.late')\n"
        "telemetry.capture_event('test.early')\n"
        "threading.Thread(target=late).start()\n"
    )

    _ = run_script(code, slow_endpoint, tmp_path)

    for event in ("test.early", "test.late"):
        assert slow_endpoint.scarf_events().count(event) == 1
        assert sum(body.count(f'"{event}"'.encode()) for body in slow_endpoint.posthog_bodies()) == 1


def test_exit_waits_a_bounded_time_for_an_unresponsive_endpoint(hanging_endpoint: Collector, tmp_path: Path) -> None:
    code = "for _ in range(3):\n    telemetry.capture_event('test.exit', {'status': 'success'})\n"

    elapsed = run_script(code, hanging_endpoint, tmp_path)

    # Our flush and PostHog's each wait at most 1 s; sending inline would block 3 s per Scarf event.
    assert elapsed < 6


@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is POSIX only")
def test_forked_children_send_their_own_events_once(slow_endpoint: Collector, tmp_path: Path) -> None:
    # The fork happens while the parent's worker is creating its clients and sending its first event,
    # with a second event still queued: the child must neither hang nor resend the parent's events, and
    # its exit must send its own. Only Scarf is checked: PostHog's exit flush is an `atexit` handler, which
    # a multiprocessing child skips.
    code = (
        "import multiprocessing\n"
        "def child():\n"
        "    telemetry.capture_event('test.child')\n"
        "if __name__ == '__main__':\n"
        "    telemetry.capture_event('test.parent')\n"
        "    telemetry.capture_event('test.parent')\n"
        "    process = multiprocessing.get_context('fork').Process(target=child)\n"
        "    process.start()\n"
        "    process.join()\n"
        "    assert process.exitcode == 0\n"
    )

    _ = run_script(code, slow_endpoint, tmp_path)

    events = slow_endpoint.scarf_events()
    assert events.count("test.parent") == 2
    assert events.count("test.child") == 1


def test_opt_out_sends_nothing_and_starts_no_thread(slow_endpoint: Collector, tmp_path: Path) -> None:
    code = (
        "import threading\n"
        "telemetry.capture_event('test.disabled')\n"
        "assert not any(thread.name == 'notte-telemetry' for thread in threading.enumerate())\n"
        "assert telemetry._clients.cache_info().currsize == 0\n"
    )

    _ = run_script(code, slow_endpoint, tmp_path, disable=True)

    assert slow_endpoint.requests == []
