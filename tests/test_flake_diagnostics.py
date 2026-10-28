"""Failed attempts survive successful reruns without contacting an API or browser."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from notte_browser.session import NotteSession
from notte_core.dom_tree import NodeSelectors
from notte_core.snapshot import SnapshotMetadata
from notte_sdk.endpoints.sessions import RemoteSession

from tests import flake_diagnostics

pytest_plugins = ["pytester"]
ROOT = Path(__file__).resolve().parents[1]


def run_case(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    *,
    target: bool = True,
    capture_fails: bool = False,
    extra_args: tuple[str, ...] = (),
) -> pytest.RunResult:
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("DISABLE_TELEMETRY", "true")
    monkeypatch.setenv("FIXTURE_DIAGNOSTIC_KEY", "fixture-diagnostic-key-value")
    pytester.makeini("[pytest]\n")
    pytester.makeconftest(
        f"""
        import sys
        from unittest.mock import MagicMock

        sys.path.insert(0, {str(ROOT)!r})
        import tests.flake_diagnostics as diagnostics
        from notte_browser.session import NotteSession
        from notte_core.snapshot import SnapshotMetadata
        from notte_sdk.endpoints.sessions import RemoteSession
        from notte_sdk.endpoints.page import PageClient
        from notte_sdk.types import SessionResponse

        pytest_plugins = ["tests.flake_diagnostics"]
        diagnostics.TARGETS = {{"test_case.py::test_target"}} if {target!r} else set()
        LIFECYCLE = []

        def start(session, *args, **kwargs):
            session._diagnostic_original_retries = session.client.root_client.max_retries
            session.response = SessionResponse.model_validate({{
                "session_id": "fixture-session",
                "idle_timeout_minutes": 3,
                "created_at": "2026-10-13T00:00:00Z",
                "last_accessed_at": "2026-10-13T00:00:00Z",
                "status": "active",
            }})

        def stop(session, **kwargs):
            assert session.client.root_client.max_retries == session._diagnostic_original_retries
            LIFECYCLE.append("remote-stop")
            session.response.status = "closed"

        def observe(page, endpoint, *, timeout):
            LIFECYCLE.append("remote-observe")
            assert endpoint.path == "/sessions/fixture-session/page/observe"
            assert timeout == diagnostics._REMOTE_CAPTURE_TIMEOUT_SECONDS
            assert page.root_client.max_retries == 0
            if {capture_fails!r}:
                assert list(diagnostics.ARTIFACT_PATH.glob("*/attempt-*/before-cleanup-error.txt"))
                raise RuntimeError("observation capture unavailable")
            result = MagicMock()
            result.metadata = SnapshotMetadata.model_validate({{
                "url": "https://www.notte.cc",
                "title": "Public fixture",
                "viewport": {{"scroll_x": 0, "scroll_y": 0, "viewport_width": 1280,
                             "viewport_height": 720, "total_width": 1280, "total_height": 720}},
                "tabs": [],
            }})
            result.space.interaction_actions = []
            return result

        async def local_start(session):
            session._window = MagicMock()
            session._window.page.url = "https://example.com"
            session._window.page.is_closed.return_value = False
            def on(event, callback):
                if event == "pageerror":
                    callback("fixture page error")
            session._window.page.on.side_effect = on

        async def local_stop(session):
            LIFECYCLE.append("local-stop")
            session._window = None

        RemoteSession.start = start
        RemoteSession.stop = stop
        PageClient.request = observe
        RemoteSession.execute = MagicMock(return_value=MagicMock(success=True))
        NotteSession.astart = local_start
        NotteSession.astop = local_stop
        """
    )
    pytester.makepyfile(test_case=source)
    return pytester.runpytest_subprocess(
        "-p",
        "pytest_rerunfailures",
        "-p",
        "pytest_asyncio.plugin",
        "--reruns=1",
        "--rerun-show-tracebacks",
        *extra_args,
        timeout=60,
    )


def attempts(pytester: pytest.Pytester) -> list[Path]:
    return sorted((pytester.path / flake_diagnostics.ARTIFACT_PATH).glob("*/attempt-*"))


def test_successful_rerun_keeps_failure_after_sdk_context_closed(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_case(
        pytester,
        monkeypatch,
        """
        import pytest
        from notte_sdk import NotteClient
        from notte_sdk.endpoints.sessions import RemoteSession
        from conftest import LIFECYCLE

        def test_target(request, monkeypatch):
            attempt = request.node.execution_count
            with NotteClient(api_key="fixture-diagnostic-key-value") as client:  # pragma: allowlist secret
                monkeypatch.setattr(client.sessions.page, "scrape", lambda *args, **kwargs: "" if attempt == 1 else "page")
                data = client.scrape(url="https://www.notte.cc")
            if attempt == 1:
                assert LIFECYCLE[-2:] == ["remote-observe", "remote-stop"]
            else:
                assert LIFECYCLE[-1:] == ["remote-stop"]
                assert LIFECYCLE.count("remote-observe") == 1
            assert data, "first attempt scrape was empty"
        """,
        extra_args=("-p", "xdist.plugin", "-n", "2"),
    )
    result.assert_outcomes(passed=1)
    assert result.ret == pytest.ExitCode.OK
    assert result.parseoutcomes()["rerun"] == 1
    assert "first attempt scrape was empty" in result.stdout.str()
    retained = attempts(pytester)
    assert len(retained) == 1
    assert retained[0].name.startswith("attempt-1-call-")
    assert "first attempt scrape was empty" in (retained[0] / "failure.txt").read_text()
    assert (retained[0] / "session-id.txt").read_text() == "fixture-session"
    assert json.loads((retained[0] / "session.json").read_text())["status"] == "active"
    assert "before-cleanup-error.txt" not in {path.name for path in retained[0].iterdir()}


def test_final_failure_keeps_both_original_errors_and_artifacts(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_case(
        pytester,
        monkeypatch,
        """
        import os
        from notte_sdk import NotteClient

        def test_target(request):
            with NotteClient(api_key=os.environ["FIXTURE_DIAGNOSTIC_KEY"]) as client:
                with client.Session():
                    raise ValueError(f"original failure attempt {request.node.execution_count}: "
                                     + os.environ["FIXTURE_DIAGNOSTIC_KEY"]
                                     + " https://private-user:private-password@example.com/private-path?token=query-value#fragment-value")  # pragma: allowlist secret
        """,
    )
    result.assert_outcomes(failed=1)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert result.parseoutcomes()["rerun"] == 1
    retained = attempts(pytester)
    assert len(retained) == 2
    for attempt, directory in enumerate(retained, start=1):
        assert directory.name.startswith(f"attempt-{attempt}-call-")
        original = f"original failure attempt {attempt}"
        assert original in (directory / "before-cleanup-error.txt").read_text()
        assert original in (directory / "failure.txt").read_text()
        text = "\n".join(path.read_text() for path in directory.iterdir())
        assert "[REDACTED]" in text
        for private in (
            "fixture-diagnostic-key-value",
            "private-user",
            "private-password",
            "private-path",
            "query-value",
            "fragment-value",
        ):
            assert private not in text


def test_capture_failure_preserves_test_failure_and_other_diagnostics(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_case(
        pytester,
        monkeypatch,
        """
        from notte_sdk import NotteClient
        from conftest import LIFECYCLE

        def test_target():
            with NotteClient(api_key="fixture-diagnostic-key-value") as client:  # pragma: allowlist secret
                with client.Session():
                    assert False, "original assertion"
        """,
        capture_fails=True,
    )
    result.assert_outcomes(failed=1)
    assert result.parseoutcomes()["rerun"] == 1
    for directory in attempts(pytester):
        assert "AssertionError: original assertion" in (directory / "failure.txt").read_text()
        assert (directory / "session-id.txt").read_text() == "fixture-session"
        assert json.loads((directory / "session.json").read_text())["status"] == "active"
        assert "observation capture unavailable" in (directory / "observation.txt.capture-error.txt").read_text()


def test_local_capture_happens_before_cleanup_and_survives_rerun(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_case(
        pytester,
        monkeypatch,
        """
        import pytest
        from notte_browser.session import NotteSession
        from conftest import LIFECYCLE

        @pytest.mark.asyncio
        async def test_target(request):
            async with NotteSession():
                pass
            assert LIFECYCLE[-1] == "local-stop"
            assert request.node.execution_count > 1, "failure after local cleanup"
        """,
    )
    result.assert_outcomes(passed=1)
    assert result.parseoutcomes()["rerun"] == 1
    retained = attempts(pytester)
    assert len(retained) == 1
    assert json.loads((retained[0] / "session.json").read_text())["page_closed"] is False
    assert "pageerror fixture page error" in (retained[0] / "events.txt").read_text()


def test_artifact_write_failure_keeps_original_pytest_error(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run_case(
        pytester,
        monkeypatch,
        """
        from notte_sdk import NotteClient
        import tests.flake_diagnostics as diagnostics

        def test_target(monkeypatch):
            def fail_write(self, *args, **kwargs):
                raise OSError("fixture artifact store unavailable")
            monkeypatch.setattr(diagnostics.Diagnostics, "write", fail_write)
            with NotteClient(api_key="fixture-diagnostic-key-value") as client:  # pragma: allowlist secret
                with client.Session():
                    raise ValueError("original test failure")
        """,
    )
    result.assert_outcomes(failed=1)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert "ValueError: original test failure" in result.stdout.str()
    assert "diagnostics capture failed" in result.stdout.str()
    assert "fixture artifact store unavailable" in result.stdout.str()
    assert attempts(pytester) == []


@pytest.mark.parametrize("selected, succeeds", [(True, True), (False, False)])
def test_passing_or_unselected_tests_leave_no_artifacts(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, selected: bool, succeeds: bool
) -> None:
    result = run_case(
        pytester,
        monkeypatch,
        f"""
        from notte_sdk import NotteClient

        def test_target():
            with NotteClient(api_key="fixture-diagnostic-key-value") as client:  # pragma: allowlist secret
                with client.Session():
                    assert {succeeds!r}, "unselected failure"
        """,
        target=selected,
    )
    if succeeds:
        result.assert_outcomes(passed=1)
    else:
        result.assert_outcomes(failed=1)
        assert result.parseoutcomes()["rerun"] == 1
    assert attempts(pytester) == []


@pytest.mark.asyncio
async def test_local_diagnostics_exclude_html_values_and_unrelated_page_content() -> None:
    session = MagicMock(spec=NotteSession)
    session.page.url = "https://example.com"
    session.page.is_closed.return_value = False
    session.trajectory = MagicMock()
    session.trajectory.last_observation = None
    session.trajectory.last_result = None
    node = MagicMock()
    node.id = "B1"
    node.get_role_str.return_value = "button"
    node.computed_attributes.selectors = NodeSelectors(
        css_selector="html > body > button",
        xpath_selector="/html/body/button",
        in_iframe=False,
        in_shadow_root=False,
        iframe_parent_css_selectors=[],
    )
    node.attributes.value = "private-input-value"
    node.state.value = "private-state-value"
    session.snapshot.metadata.url = "https://example.com"
    session.snapshot.html_content = "private-raw-html"
    session.snapshot.interaction_nodes.return_value = [node]
    diagnostics = flake_diagnostics.Diagnostics()
    await diagnostics.local(session)
    nodes = json.loads(diagnostics.files["nodes.json"])
    assert nodes[0]["id"] == "B1"
    assert nodes[0]["selectors"]["css_selector"] == "html > body > button"
    text = "\n".join(diagnostics.files.values())
    assert "private-input-value" not in text
    assert "private-state-value" not in text
    assert "private-raw-html" not in text

    session.page.url = "https://unrelated.example.test/customer"
    session.snapshot.metadata.url = session.page.url
    session.page.evaluate.reset_mock()
    diagnostics = flake_diagnostics.Diagnostics()
    await diagnostics.local(session)
    assert "outside the public test hosts" in diagnostics.files["nodes.json"]
    session.page.evaluate.assert_not_called()


def test_remote_diagnostics_exclude_response_secrets_and_unrelated_observations() -> None:
    session = MagicMock(spec=RemoteSession)
    session.session_id = "fixture-session"
    session.response = MagicMock(status="active", close_reason=None, error=None)
    session.client = MagicMock()
    session.client.root_client.max_retries = 3
    session.response.cdp_url = "wss://private-browser.example.test/?token=private-cdp-token"
    session.response.steps = ["private-session-history"]
    observed = session.client.page.request.return_value
    observed.metadata = SnapshotMetadata.model_validate(
        {
            "url": "https://www.notte.cc",
            "title": "Public fixture",
            "viewport": {
                "scroll_x": 0,
                "scroll_y": 0,
                "viewport_width": 1280,
                "viewport_height": 720,
                "total_width": 1280,
                "total_height": 720,
            },
            "tabs": [],
        }
    )
    action = MagicMock()
    action.id = "B1"
    action.type = "click"
    action.selector.playwright_selector = "css=button"
    observed.space.interaction_actions = [action]
    observed.element_states = {"I1": "private-input-value"}
    diagnostics = flake_diagnostics.Diagnostics()
    diagnostics.remote(session)
    assert "css=button" in diagnostics.files["observation.txt"]
    assert "private-" not in "\n".join(diagnostics.files.values())
    assert session.client.root_client.max_retries == 3
    session.status.assert_not_called()

    session.client.page.request.return_value.metadata.url = "https://unrelated.example.test/customer"
    diagnostics = flake_diagnostics.Diagnostics()
    diagnostics.remote(session)
    assert json.loads(diagnostics.files["session.json"]) == {
        "kind": "remote",
        "session_id": "fixture-session",
        "status": "active",
        "status_source": "cached response before cleanup",
        "close_reason": None,
        "error": None,
    }
    assert "outside the public test hosts" in diagnostics.files["observation.txt"]
    assert "private-" not in "\n".join(diagnostics.files.values())

    session.client.page.request.side_effect = RuntimeError("capture unavailable")
    diagnostics.remote(session)
    assert session.client.root_client.max_retries == 3
    assert "capture unavailable" in diagnostics.files["observation.txt.capture-error.txt"]


def test_json_artifacts_remain_valid_after_redaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIXTURE_DIAGNOSTIC_KEY", "fixture-key-value")
    item = MagicMock(spec=pytest.Item)
    item.config = MagicMock()
    item.config.rootpath = tmp_path
    item.nodeid = "test_case.py::test_target"
    item.execution_count = 1
    diagnostics = flake_diagnostics.Diagnostics()
    directory = diagnostics.write(
        item,
        "call",
        {
            "result.json": json.dumps(
                {
                    "success": False,
                    "message": "original error password=private-inline-value fixture-key-value",
                    "url": "https://private-user:private-password@example.com/private-path?token=private-query",  # pragma: allowlist secret
                }
            )
        },
    )
    value = json.loads((directory / "result.json").read_text())
    assert value["success"] is False
    assert "original error" in value["message"]
    assert value["url"] == "https://example.com"
    assert "private-" not in json.dumps(value)
    assert "fixture-key-value" not in json.dumps(value)


@pytest.mark.parametrize("name", ["oversized.txt", "oversized.json"])
def test_redaction_precedes_truncation_at_secret_boundary(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "boundary-private-environment-credential"  # pragma: allowlist secret
    monkeypatch.setenv("FIXTURE_DIAGNOSTIC_KEY", secret)
    text = "x" * 63_995 + secret + "y" * 100
    if name.endswith(".json"):
        text = json.dumps({"message": "x" * 63_980 + secret + "y" * 100})
    diagnostics = flake_diagnostics.Diagnostics()
    diagnostics.record(name, lambda: text)
    retained = diagnostics.files[name]
    assert json.loads(retained)["truncated"] is True
    assert "bound" not in retained


def test_live_workflow_retains_diagnostics_after_successful_reruns() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/test-cicd.yml").read_text())
    steps = workflow["jobs"]["staging-and-live"]["steps"]
    run = next(step for step in steps if step.get("name") == "Run staging and live tests")
    assert "--rerun-show-tracebacks" in run["run"]
    upload = next(step for step in steps if step.get("name") == "Upload failed-attempt diagnostics")
    assert upload["if"] == "${{ always() }}"
    assert upload["with"]["path"] == f"{flake_diagnostics.ARTIFACT_PATH}/"
    assert upload["with"]["include-hidden-files"] is True
    assert "${{ matrix.shard }}" in upload["with"]["name"]


def test_redaction_covers_auth_headers_secrets_and_url_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIXTURE_DIAGNOSTIC_KEY", "fixture-key-value")
    value = flake_diagnostics.redact(
        "original browser error fixture-key-value\n"
        "Authorization: Basic private-basic-value\n"
        "Cookie: sid=private-cookie-value\n"
        "Bearer private-bearer-value\n"
        "api_key=private-inline-value\n"
        "https://private-user:private-password@example.com/private-path?token=private-query#private-fragment"  # pragma: allowlist secret
    )
    assert value.splitlines() == [
        "original browser error [REDACTED]",
        "[REDACTED]",
        "[REDACTED]",
        "Bearer [REDACTED]",
        "[REDACTED]",
        "https://example.com",
    ]
    assert "fixture-key-value" not in value
    assert "private-" not in value


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://example.com.attacker.invalid/private-path?token=private-query#private-fragment",
            "https://example.com.attacker.invalid",
        ),
        (
            "https://example.com@attacker.invalid/private-path?token=private-query",
            "https://attacker.invalid",
        ),
        (
            "https://attacker.invalid/private-path/https://example.com?next=private-query",
            "https://attacker.invalid",
        ),
        (
            "HTTPS://private-user:private-password@EXAMPLE.COM/private-path?token=private-query",  # pragma: allowlist secret
            "https://example.com",
        ),
        (
            "WsS://private-user:private-password@EXAMPLE.COM/private-path?token=private-query",  # pragma: allowlist secret
            "wss://example.com",
        ),
        (
            "https://private%40user:private%3Apassword@example.com/private-path",  # pragma: allowlist secret
            "https://example.com",
        ),
        (
            "https://example.com:8443/private-path?token=private-query",
            "https://example.com",
        ),
        (
            "https://[private-authority/private-path?token=private-query",
            "[REDACTED URL]",
        ),
    ],
)
def test_url_redaction_retains_only_parsed_scheme_and_hostname(url: str, expected: str) -> None:
    assert flake_diagnostics.redact(url) == expected
