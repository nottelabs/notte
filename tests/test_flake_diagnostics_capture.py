"""Action-only sessions retain bounded diagnostic reads without changing actions."""

import json

import pytest
from notte_browser.session import NotteSession
from patchright.async_api import Route

from tests import flake_diagnostics
from tests.test_flake_diagnostics import attempts, run_case

pytest_plugins = ["pytester"]


@pytest.mark.asyncio
async def test_uncached_dom_read_is_bounded_and_excludes_values() -> None:
    async def serve(route: Route) -> None:
        await route.fulfill(
            body="<html><head><title>Local fixture</title></head><body>"
            '<input value="private-input-value"><script>const text = "private-script-value";</script>'
            + ('<div role="' + "x" * 100 + '">private-text-value</div>') * 700
            + "</body></html>",
            content_type="text/html",
        )

    async with NotteSession(headless=True) as session:
        await session.page.route("https://example.com/**", serve)
        _ = await session.page.goto("https://example.com", wait_until="domcontentloaded")
        state = flake_diagnostics.Diagnostics()
        await state.local(session)
        assert session._snapshot is None
        assert session.trajectory.last_observation is None
    nodes = json.loads(state.files["nodes.json"])
    assert nodes["truncated"] is True
    assert len(nodes["nodes"]) == 500
    assert all(set(node) == {"tag", "parent"} for node in nodes["nodes"])
    assert nodes["nodes"][0] == {"tag": "HTML", "parent": None}
    assert json.loads(state.files["observation.json"])["title"] == "Local fixture"
    assert "private-" not in "\n".join(state.files.values())


def test_action_only_failure_captures_structure_before_cleanup(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_case(
        pytester,
        monkeypatch,
        """
        import json
        import pytest
        from unittest.mock import AsyncMock
        from notte_browser.errors import NoSnapshotObservedError
        from notte_browser.session import NotteSession
        from tests.mock.snapshot_factory import make_snapshot
        import tests.flake_diagnostics as diagnostics
        from conftest import LIFECYCLE

        @pytest.mark.asyncio
        async def test_target(request):
            async with NotteSession() as session:
                assert session.trajectory.last_observation is None
                with pytest.raises(NoSnapshotObservedError):
                    _ = session.snapshot
                metadata = AsyncMock(return_value=make_snapshot("https://example.com").metadata)
                session.window.snapshot_metadata = metadata

                async def read_structure(script):
                    assert "local-stop" not in LIFECYCLE
                    assert list(diagnostics.ARTIFACT_PATH.glob("*/attempt-*/before-cleanup-error.txt"))
                    assert "createTreeWalker" in script and "nodes.length < 500" in script
                    return json.dumps({"nodes": [{"tag": "A", "parent": None}], "truncated": False})

                structure = AsyncMock(side_effect=read_structure)
                session.page.evaluate = structure
                session.aexecute = AsyncMock()
                session.aobserve = AsyncMock(side_effect=AssertionError("must not observe"))
                await session.aexecute(type="goto", url="https://example.com")
                await session.aexecute(type="evaluate_js", code="document.title")
                assert request.node.execution_count > 1, "original evaluate assertion"

            # A successful action-only attempt needs no fresh diagnostic reads.
            metadata.assert_not_awaited()
            structure.assert_not_awaited()
            session.aobserve.assert_not_awaited()
            assert session.aexecute.await_count == 2
            assert session._snapshot is None
            assert LIFECYCLE[-1] == "local-stop"
        """,
    )
    result.assert_outcomes(passed=1)
    assert result.parseoutcomes()["rerun"] == 1
    retained = attempts(pytester)
    assert len(retained) == 1
    directory = retained[0]
    assert "original evaluate assertion" in (directory / "failure.txt").read_text()
    assert json.loads((directory / "observation.json").read_text())["url"] == "https://example.com"
    assert json.loads((directory / "nodes.json").read_text()) == {
        "nodes": [{"tag": "A", "parent": None}],
        "truncated": False,
    }
    assert not list(directory.glob("*.capture-error.txt"))


@pytest.mark.parametrize("mode", ["error", "timeout", "cancel", "interrupt"])
def test_action_only_capture_failure_preserves_original_and_cleanup(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    result = run_case(
        pytester,
        monkeypatch,
        f"""
        import asyncio
        import pytest
        from unittest.mock import AsyncMock
        from notte_browser.session import NotteSession
        from tests.mock.snapshot_factory import make_snapshot
        import tests.flake_diagnostics as diagnostics
        from conftest import LIFECYCLE

        @pytest.mark.asyncio
        async def test_target(monkeypatch):
            monkeypatch.setattr(diagnostics, "_LOCAL_CAPTURE_TIMEOUT_SECONDS", 0.01)
            try:
                async with NotteSession() as session:
                    session.window.snapshot_metadata = AsyncMock(
                        return_value=make_snapshot("https://example.com").metadata)

                    async def read_structure(script):
                        assert list(diagnostics.ARTIFACT_PATH.glob("*/attempt-*/before-cleanup-error.txt"))
                        try:
                            if {mode!r} == "timeout":
                                await asyncio.Event().wait()
                            elif {mode!r} == "cancel":
                                raise asyncio.CancelledError("diagnostic cancellation")
                            elif {mode!r} == "interrupt":
                                raise KeyboardInterrupt("diagnostic interruption")
                            else:
                                raise RuntimeError("diagnostic read failed")
                        finally:
                            LIFECYCLE.append("capture-finished")

                    structure = AsyncMock(side_effect=read_structure)
                    session.page.evaluate = structure
                    raise ValueError("original action-only failure")
            finally:
                assert LIFECYCLE[-2:] == ["capture-finished", "local-stop"]
                structure.assert_awaited_once()
        """,
    )
    result.assert_outcomes(failed=1)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert result.parseoutcomes()["rerun"] == 1
    retained = attempts(pytester)
    assert len(retained) == 2
    for directory in retained:
        assert "ValueError: original action-only failure" in (directory / "failure.txt").read_text()
        assert "ValueError: original action-only failure" in (directory / "before-cleanup-error.txt").read_text()
        capture_errors = list(directory.glob("*.capture-error.txt"))
        assert capture_errors
        text = "\n".join(path.read_text() for path in capture_errors)
        assert {
            "error": "diagnostic read failed",
            "timeout": "TimeoutError",
            "cancel": "CancelledError",
            "interrupt": "KeyboardInterrupt",
        }[mode] in text
