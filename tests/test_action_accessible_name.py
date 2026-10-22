"""`InteractionAction.accessible_name`: an optional field of the observed actions, compatible both ways."""

import json

from notte_core.actions import ClickAction, FillAction
from notte_core.space import ActionSpace


def _space() -> ActionSpace:
    return ActionSpace(
        description='I1[:]<input name="email"></input>\nB1[:]<button>Send</button>',
        interaction_actions=[
            FillAction(id="I1", value="<sample_value>", text_label="email", accessible_name="Email address"),
            ClickAction(id="B1", text_label="Send"),
        ],
    )


def test_accessible_names_round_trip() -> None:
    parsed = ActionSpace.model_validate_json(_space().model_dump_json())
    assert [(a.text_label, a.accessible_name) for a in parsed.interaction_actions] == [
        ("email", "Email address"),
        ("Send", None),
    ]


def test_a_payload_without_the_field_parses() -> None:
    # an observe response from a server that does not compute names
    payload = json.loads(_space().model_dump_json())
    for action in payload["interaction_actions"]:
        del action["accessible_name"]
    parsed = ActionSpace.model_validate(payload)
    assert [a.accessible_name for a in parsed.interaction_actions] == [None, None]


def test_an_older_client_ignores_the_field() -> None:
    # older clients parse actions with these classes minus the field: unknown fields are ignored
    payload = json.loads(_space().model_dump_json())["interaction_actions"][0]
    payload["a_field_this_client_does_not_know"] = "ignored"
    action = FillAction.model_validate(payload)
    assert action.text_label == "email" and action.accessible_name == "Email address"
