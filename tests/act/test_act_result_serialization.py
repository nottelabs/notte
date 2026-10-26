"""Act results retain the chosen action when stored or sent as JSON."""

import json
from typing import Literal

import pytest
from notte_core.act import ActResult
from notte_core.actions import ClickAction, FillAction, SelectDropdownOptionAction, WaitAction


@pytest.mark.parametrize(
    "action",
    [
        ClickAction(id="B1", selector="#submit"),
        FillAction(id="I1", selector="#name", value="Jane"),
        SelectDropdownOptionAction(id="S1", selector="#country", value="fr"),
        WaitAction(time_ms=100),
    ],
)
def test_act_result_preserves_the_exact_action_payload(
    action: ClickAction | FillAction | SelectDropdownOptionAction | WaitAction,
) -> None:
    result = ActResult(instruction="Complete the form", status="proposed", action=action)
    assert result.model_dump()["action"] == action.model_dump()
    assert json.loads(result.model_dump_json())["action"] == json.loads(action.model_dump_json())
    restored = ActResult.model_validate_json(result.model_dump_json())
    assert type(restored.action) is type(action)
    assert restored.action == action


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_act_result_action_schema_keeps_concrete_discriminated_actions(
    mode: Literal["validation", "serialization"],
) -> None:
    schema = ActResult.model_json_schema(mode=mode)
    action_schema = schema["properties"]["action"]["anyOf"][0]
    assert action_schema["discriminator"]["propertyName"] == "type"
    click_ref = action_schema["discriminator"]["mapping"]["click"]
    click = schema["$defs"][click_ref.rsplit("/", 1)[-1]]
    assert {"type", "id", "selector"} <= click["properties"].keys()
