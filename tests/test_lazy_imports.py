"""Importing the packages stays cheap: heavy optional libraries load only when a feature needs them."""

import subprocess
import sys
import textwrap

import pytest

# Each is imported on first use: screenshot decoding/drawing (Pillow), enabled profiling (OpenTelemetry),
# vault URL checks (tldextract) and the scrape fallback for pages without a main content element (trafilatura).
LAZY_MODULES = ("PIL", "opentelemetry", "tldextract", "trafilatura")


def _run(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, timeout=120, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize("package", ["notte_sdk", "notte"])
def test_import_does_not_load_heavy_dependencies(package: str) -> None:
    loaded = _run(
        f"""
        import sys
        import {package}
        print(",".join(name for name in {LAZY_MODULES!r} if name in sys.modules))
        """
    ).strip()
    assert loaded == "", f"`import {package}` loaded {loaded}"


def test_root_domain_uses_the_bundled_suffix_list_without_network() -> None:
    output = _run(
        """
        import socket

        def no_network(*args, **kwargs):
            raise AssertionError("tldextract tried to reach the network")

        socket.socket.connect = no_network
        socket.getaddrinfo = no_network

        from notte_core.url import get_root_domain

        print(get_root_domain("https://login.example.co.uk/path"), get_root_domain("https://app.neo.space/mail/"))
        """
    )
    assert output.split() == ["example.co.uk", "neo.space"]


def test_bounding_box_import_path_is_unchanged() -> None:
    from notte_core.browser.geometry import BoundingBox
    from notte_core.browser.highlighter import BoundingBox as HighlighterBoundingBox

    assert HighlighterBoundingBox is BoundingBox


def test_enabled_profiler_records_spans() -> None:
    pytest.importorskip("opentelemetry.sdk")
    # A subprocess keeps the global OpenTelemetry tracer provider out of the test session.
    output = _run(
        """
        from notte_core.profiling import NotteProfiler

        profiler = NotteProfiler(default_service_name="test")
        profiler.enable = True

        @profiler.profiled()
        def work():
            return 42

        assert work() == 42
        with profiler.profile_sync("block", attributes={"key": "value"}):
            pass
        spans = profiler.get_span_data()
        print(sorted(span["name"] for span in spans))
        """
    )
    assert output.strip() == "['block', 'work']"


def test_local_session_can_be_constructed_without_sdk() -> None:
    _run(
        """
        import sys

        sys.modules["notte_sdk"] = None

        import os
        os.environ["DISABLE_TELEMETRY"] = "true"

        from notte_browser.session import NotteSession

        session = NotteSession()
        assert session.persona is None
        assert session.vault is None
        assert session._window is None
        assert sys.modules["notte_sdk"] is None
        assert not any(name.startswith("notte_sdk.") for name in sys.modules)
        """
    )
