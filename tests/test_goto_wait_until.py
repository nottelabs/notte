"""`goto` accepts a `wait_until` navigation event and omits it from the wire when unset."""

import datetime as dt
from typing import Literal

import pytest
from notte_browser.session import NotteSession
from notte_core.actions import ActionUnion, GotoAction
from notte_core.actions.typedicts import action_dict_to_base_action
from notte_core.browser.observation import ExecutionResult
from pydantic import BaseModel, TypeAdapter, ValidationError


def test_goto_action_defaults_to_no_wait_until_and_wire_dump_omits_it() -> None:
    action = GotoAction(url="https://example.com")

    assert action.wait_until is None
    # SDK requests and API responses use exclude_none at their wire boundaries.
    assert "wait_until" not in action.model_dump(exclude_none=True)
    assert GotoAction(url="https://example.com", wait_until="commit").model_dump()["wait_until"] == "commit"


def test_goto_action_union_serialization_schema_remains_concrete() -> None:
    schema = TypeAdapter(ActionUnion).json_schema(mode="serialization")
    goto_schema = schema["$defs"]["GotoAction"]

    assert schema["discriminator"]["mapping"]["goto"] == "#/$defs/GotoAction"
    assert goto_schema["type"] == "object"
    assert {"type", "url", "wait_until"} <= goto_schema["properties"].keys()
    assert goto_schema["properties"]["type"]["const"] == "goto"


class _GotoBeforeWaitUntil(BaseModel):
    """The goto action as every SDK released before this field parses it."""

    type: Literal["goto"] = "goto"
    url: str
    model_config = {"extra": "forbid"}


def test_an_echoed_goto_still_parses_on_an_older_sdk() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    result = ExecutionResult(
        action=GotoAction(url="https://example.com"), success=True, message="ok", started_at=now, ended_at=now
    )

    # API response routes exclude None-valued model fields at the wire boundary.
    echoed = result.model_dump(mode="json", by_alias=True, exclude_none=True)["action"]

    parsed = _GotoBeforeWaitUntil.model_validate(
        {k: v for k, v in echoed.items() if k in ("type", "url", "wait_until")}
    )
    assert parsed.url == "https://example.com"


def test_goto_action_accepts_the_playwright_events_only() -> None:
    assert GotoAction(url="https://example.com", wait_until="commit").wait_until == "commit"
    assert (
        action_dict_to_base_action(
            {"type": "goto", "url": "https://example.com", "wait_until": "domcontentloaded"}
        ).wait_until
        == "domcontentloaded"
    )  # type: ignore[attr-defined]
    with pytest.raises(ValidationError):
        _ = GotoAction(url="https://example.com", wait_until="eventually")  # type: ignore[arg-type]


def test_wait_until_stays_out_of_the_agent_schema() -> None:
    # the agent prompt renders each action's schema minus non_agent_fields; keep the knob out of it
    assert "wait_until" in GotoAction.non_agent_fields()
    assert "wait_until" not in GotoAction(url="https://example.com", wait_until="commit").model_dump_agent()


@pytest.mark.asyncio
async def test_goto_with_commit_is_enough_for_a_same_origin_fetch() -> None:
    async with NotteSession(headless=True) as session:
        result = await session.aexecute(type="goto", url="https://www.example.com/", wait_until="commit")
        assert result.success

        response = await session.afetch("/")

        assert response.status_code == 200
        assert "Example Domain" in response.text
