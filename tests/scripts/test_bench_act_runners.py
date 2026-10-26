"""Benchmark read failures preserve evidence without converting incomplete runs into passes."""

import json
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from notte_browser.driver import Error
from notte_core.act import ActResult

from scripts.bench_act import runners
from scripts.bench_act.model import Probe, Task


@pytest.fixture
def runner_session(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock, Mock]:
    page = MagicMock()
    page.url = "http://fixture.test/finished.html"
    page.context.pages = [page]
    page.wait_for_load_state = AsyncMock()
    session = MagicMock()
    session.__aenter__.return_value = session
    session.window.page = page
    session.aexecute = AsyncMock()
    session.aact = AsyncMock(return_value=ActResult(instruction="Finish", status="done", operation="DONE"))
    decider = Mock()
    monkeypatch.setattr(runners, "NotteSession", Mock(return_value=session))
    monkeypatch.setattr(runners, "notte_decider", Mock(return_value=decider))
    return session, page, decider


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["navigation", "persistent-navigation", "other", "invalid-json", "extra"])
async def test_final_read_preserves_run_evidence(
    runner_session: tuple[MagicMock, MagicMock, Mock], failure: str
) -> None:
    session, page, decider = runner_session
    landing = {"url": page.url, "status": 200, "text": "Landing evidence"}
    final = {"url": page.url, "text": "Task completed"}
    navigation = Error("Execution context was destroyed, most likely because of a navigation")
    if failure == "navigation":
        outputs = [json.dumps(landing), navigation, json.dumps(final)]
    elif failure == "persistent-navigation":
        outputs = [json.dumps(landing), navigation, navigation]
    elif failure == "other":
        outputs = [json.dumps(landing), Error("Page read failed")]
    elif failure == "invalid-json":
        outputs = [json.dumps(landing), "not JSON"]
    else:
        outputs = [json.dumps(landing), json.dumps(final), Error("Extra state unavailable")]
    page.evaluate = AsyncMock(side_effect=outputs)
    task = Task(
        "finish",
        page.url,
        "Finish",
        lambda f, _: f["url"] == page.url,
        max_steps=1,
        final_js="extra" if failure == "extra" else None,
    )
    run = await runners.run_task(task, page.url, "scripted", "accessible")
    assert run["landing"] == landing
    assert len(run["steps"]) == 1 and run["steps"][0]["status"] == "done"
    assert run["wall_ms"] >= 0 and run["session_start_ms"] >= 0
    session.aact.assert_awaited_once()
    decider.close.assert_called_once()
    if failure == "navigation":
        assert run["final"] == final and "error" not in run
    else:
        assert run["error"] and "final" not in run
    assert page.wait_for_load_state.await_count == int(failure in {"navigation", "persistent-navigation"})


@pytest.mark.asyncio
async def test_failed_consent_setup_keeps_probe_landing_evidence(
    runner_session: tuple[MagicMock, MagicMock, Mock],
) -> None:
    _, page, decider = runner_session
    page.url = "https://consent.google.com/"
    landing = {"url": page.url, "status": 200, "text": "Consent"}
    page.evaluate = AsyncMock(return_value=json.dumps(landing))
    page.get_by_role.return_value.first.click = AsyncMock(side_effect=Error("Consent button unavailable"))
    probe = Probe("flight-results", "https://google.com/travel/flights/", "Are results shown?", None, "YES")
    run = await runners.run_probes([probe], probe.url, "scripted")
    assert run["landing"] == landing and run["probes"] == []
    assert "Consent button unavailable" in run["error"]
    decider.close.assert_called_once()
