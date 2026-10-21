"""`RemoteSession.act()` runs client-side on top of observe / execute (both mocked here)."""

import asyncio
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from notte_core.act import aact_until_done, act_until_done
from notte_core.actions import BaseAction, ClickAction, EvaluateJsAction, FillAction, SelectDropdownOptionAction
from notte_core.data import DataSpace
from notte_core.observation import ExecutionResult, Observation
from notte_core.snapshot import SnapshotMetadata, ViewportData
from notte_core.space import ActionSpace
from notte_sdk.endpoints.sessions import RemoteSession

from tests.act.fakes import FakeDecider

DESCRIPTION = """_[:]Search
I1[:]<input type="text" name="q"></input>
I2[:]<select name="lang"></select>
B1[:]<button type="submit">Search</button>"""


def _observation(url: str = "https://search.test/", label: str = "Search") -> Observation:
    now = dt.datetime.now(dt.timezone.utc)
    return Observation(
        metadata=SnapshotMetadata(
            title="Search",
            url=url,
            viewport=ViewportData(
                scroll_x=0, scroll_y=0, viewport_width=1280, viewport_height=720, total_width=1280, total_height=720
            ),
            tabs=[],
        ),
        screenshot=b"",
        space=ActionSpace(
            # the button renders its label, as a real observation would
            description=DESCRIPTION.replace(">Search</button>", f">{label}</button>"),
            interaction_actions=[
                FillAction(id="I1", value="<sample_value>", text_label="q", selector="xpath=html/body/form/input"),
                SelectDropdownOptionAction(
                    id="I2", value="<sample_value>", text_label="lang", selector="xpath=html/body/form/select"
                ),
                ClickAction(id="B1", text_label=label, selector="xpath=html/body/form/button"),
            ],
        ),
        started_at=now,
        ended_at=now,
    )


class _Remote:
    """observe / execute of a cloud session. `signatures` are the `evaluate_js` answers of the
    freshness check, in order (`None`: the call fails, like on an API without evaluate_js data)."""

    def __init__(self, observations: list[Observation], signatures: list[dict[str, Any] | None] | None = None) -> None:
        self.observations: list[Observation] = observations
        self.signatures: list[dict[str, Any] | None] = signatures or []
        self.executed: list[BaseAction] = []
        self.observe_calls: int = 0
        self.observe_kwargs: list[dict[str, Any]] = []
        self.js_calls: list[str] = []

    def observe(self, **kwargs: Any) -> Observation:
        self.observe_calls += 1
        self.observe_kwargs.append(kwargs)
        return self.observations.pop(0) if len(self.observations) > 1 else self.observations[0]

    def execute(
        self, action: BaseAction | None = None, *, raise_on_failure: bool | None = None, **kwargs: Any
    ) -> ExecutionResult:
        now = dt.datetime.now(dt.timezone.utc)
        if kwargs.get("type") == "evaluate_js":
            self.js_calls.append(kwargs["code"])
            answer = self.signatures.pop(0) if self.signatures else None
            js = EvaluateJsAction(code=kwargs["code"])
            if answer is None:
                return ExecutionResult(action=js, success=False, message="no data", started_at=now, ended_at=now)
            data = DataSpace(markdown=json.dumps(answer))
            return ExecutionResult(action=js, success=True, message="ok", data=data, started_at=now, ended_at=now)
        assert action is not None and raise_on_failure in (True, False)
        self.executed.append(action)
        return ExecutionResult(action=action, success=True, message="ok", started_at=now, ended_at=now)


@pytest.fixture(autouse=True)
def default_label_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTTE_ACT_LABELS", raising=False)


def _session(remote: _Remote, monkeypatch: pytest.MonkeyPatch) -> RemoteSession:
    session = RemoteSession(_client=MagicMock())
    monkeypatch.setattr(session, "observe", remote.observe)
    monkeypatch.setattr(session, "execute", remote.execute)
    return session


def test_remote_act_types_and_selects_by_label(monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _Remote([_observation()])
    session = _session(remote, monkeypatch)
    # act() always observes with the fast perception, whatever the session default
    session.default_perception_type = "deep"
    decider = FakeDecider(
        choices=[
            {"operation": "TYPE_TEXT", "type_text_target": "I1"},
            {"operation": "TYPE_TEXT", "type_text_target": "I2"},
        ],
        texts=["{{query}}", "French"],
    )

    typed = session.act("search {{query}} in French", variables={"query": "notte"}, decider=decider)
    assert typed.status == "executed" and typed.value == "{{query}}"
    assert isinstance(remote.executed[0], FillAction) and remote.executed[0].value == "notte"

    # no live state over the wire: the select is a TYPE_TEXT target, filled with the option label
    selected = session.act("search {{query}} in French", variables={"query": "notte"}, decider=decider)
    assert isinstance(selected.action, SelectDropdownOptionAction) and selected.action.value == "French"
    assert "value" not in decider.states[0].elements[0]
    # a fill without live state: page_changed is unknown, not False
    assert decider.states[1].recent_actions == [
        {
            # the accessible name (the text before the field)
            "action": "Search",
            "kind": "TYPE_TEXT",
            "text": "{{query}}",
            "page_changed": None,
        }
    ]
    assert remote.observe_kwargs and all(kw == {"perception_type": "fast"} for kw in remote.observe_kwargs)


def test_remote_act_is_stale_when_the_target_keeps_changing(monkeypatch: pytest.MonkeyPatch) -> None:
    observations = [_observation(label=f"Search {i}") for i in range(4)]
    remote = _Remote(observations)
    session = _session(remote, monkeypatch)
    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": "B1"}] * 2)

    result = session.act("click search", raise_on_failure=False, decider=decider)
    assert result.status == "stale" and remote.executed == []


def test_remote_choose_and_check(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session(_Remote([_observation()]), monkeypatch)
    decider = FakeDecider(choices=[{"answer": "b"}, {"answer": "YES"}])
    choice = session.choose("pick", {"a": "first", "b": "second"}, decider=decider)
    assert choice.choice == "b"
    assert session.check("Is it a search page?", decider=decider) == pytest.approx(0.9)


def _signatures(url: str = "https://search.test/", **elements: Any) -> dict[str, Any]:
    # `ELEMENT_SIGNATURES_JS` returns 15 entries per element: pad the ones a test does not set
    return {"url": url, "elements": {k: v + [None] * (15 - len(v)) for k, v in elements.items()}}


def test_remote_freshness_uses_two_evaluate_js_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    button = ["BUTTON", "Search", "", None, False, None, None]
    remote = _Remote(
        [_observation()],
        signatures=[_signatures(B1=button, I1=["INPUT", "", "", None, False, None, None]), _signatures(B1=button)],
    )
    session = _session(remote, monkeypatch)
    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": "B1"}])

    result = session.act("click search", decider=decider)

    assert result.status == "executed" and len(remote.executed) == 1
    # one observe, no second observe for the freshness check
    assert remote.observe_calls == 1 and len(remote.js_calls) == 2
    # all the elements after observing, then the target only
    assert '"I1": "html/body/form/input"' in remote.js_calls[0]
    assert '"B1": "html/body/form/button"' in remote.js_calls[1] and '"I1"' not in remote.js_calls[1]


def test_remote_freshness_detects_a_changed_target(monkeypatch: pytest.MonkeyPatch) -> None:
    before = _signatures(B1=["BUTTON", "Search", "", None, False, None, None])
    after = _signatures(B1=["BUTTON", "Searching...", "", None, True, None, None])
    remote = _Remote([_observation()], signatures=[before, after, before, after])
    session = _session(remote, monkeypatch)
    decider = FakeDecider(choices=[{"operation": "CLICK", "click_target": "B1"}] * 2)

    result = session.act("click search", raise_on_failure=False, decider=decider)
    assert result.status == "stale" and remote.executed == []


@pytest.mark.parametrize("asynchronous", [False, True])
def test_cloud_loop_keeps_filling_without_observable_fingerprints(
    monkeypatch: pytest.MonkeyPatch, asynchronous: bool
) -> None:
    remote = _Remote([_observation()])
    session = _session(remote, monkeypatch)
    decider = FakeDecider(
        choices=[{"operation": "TYPE_TEXT", "type_text_target": "I1"}] * 5 + [{"operation": "DONE"}],
        texts=[f"value {i}" for i in range(5)],
    )
    results = (
        asyncio.run(aact_until_done(session, "Fill the form", decider=decider))
        if asynchronous
        else act_until_done(session, "Fill the form", decider=decider)
    )
    assert len(results) == 6 and results[-1].status == "done"
    assert len(remote.executed) == 5


def test_remote_supplied_observation_is_refreshed_before_act(monkeypatch: pytest.MonkeyPatch) -> None:
    old = _observation()
    new = _observation(url="https://other.test/", label="Delete account")
    button = ["BUTTON", "Delete account", "", None, False, None, None]
    remote = _Remote([new], signatures=[_signatures(url=new.metadata.url, B1=button)] * 2)
    session = _session(remote, monkeypatch)
    decider = FakeDecider(choices=[{"operation": "DONE"}])
    _ = session.act("Review the page", observation=old, decider=decider)
    assert decider.states[0].page.url == new.metadata.url
    assert any(e.get("label") == "Delete account" for e in decider.states[0].elements)
    assert remote.executed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["choose", "check", "done", "blocked", "dry_run"])
async def test_remote_early_returns_leave_no_signature_tasks(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    completed: list[bool] = []
    errors: list[dict[str, Any]] = []
    remote = _Remote([_observation()])
    session = _session(remote, monkeypatch)

    def failing_execute(*args: Any, **kwargs: Any) -> ExecutionResult:
        time.sleep(0.02)
        completed.append(True)
        raise RuntimeError("transport unavailable")

    monkeypatch.setattr(session, "execute", failing_execute)
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    loop.set_exception_handler(lambda _, context: errors.append(context))
    try:
        if mode == "choose":
            _ = await session.achoose("Pick", ["a", "b"], decider=FakeDecider(choices=[{"answer": "a"}]))
        elif mode == "check":
            _ = await session.acheck("Yes?", decider=FakeDecider(choices=[{"answer": "YES"}]))
        else:
            choice = {"operation": mode.upper()} if mode != "dry_run" else {"operation": "CLICK", "click_target": "B1"}
            _ = await session.aact(
                "Act", decider=FakeDecider(choices=[choice]), dry_run=mode == "dry_run", raise_on_failure=False
            )
        assert len(completed) == (1 if mode in ("done", "blocked") else 0)
        await asyncio.sleep(0.05)
        assert not errors
        assert len(completed) == (1 if mode in ("done", "blocked") else 0)
    finally:
        loop.set_exception_handler(previous)


@pytest.mark.parametrize("method", ["act", "choose", "check"])
def test_act_reference_examples_use_existing_tested_snippets(method: str) -> None:
    import re

    doc = getattr(RemoteSession, method).__doc__ or ""
    assert "```python" not in doc
    snippets = re.findall(r"from '(/snippets/[^']+)';", doc)
    assert snippets
    docs = Path(__file__).resolve().parents[2] / "docs/src"
    for snippet in snippets:
        content = (docs / snippet.lstrip("/")).read_text()
        assert "@sniptest testers/" in content
