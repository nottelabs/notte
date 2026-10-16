"""Browser actions take a named parameter; the generic `value=` keyword was removed."""

from typing import Any

import pytest
from notte_core.actions import FillAction, FormFillAction, GotoAction, action_dict_to_base_action
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("data", "replacement"),
    [
        ({"type": "goto", "value": "https://example.com"}, "url"),
        ({"type": "goto_new_tab", "value": "https://example.com"}, "url"),
        ({"type": "switch_tab", "value": 1}, "tab_index"),
        ({"type": "wait", "value": 100}, "time_ms"),
        ({"type": "press_key", "value": "Enter"}, "key"),
        ({"type": "scroll_down", "value": 200}, "amount"),
        ({"type": "evaluate_js", "value": "document.title"}, "code"),
    ],
)
def test_value_names_the_parameter_to_use(data: dict[str, Any], replacement: str) -> None:
    with pytest.raises(ValidationError, match=f"use '{replacement}' instead") as exc_info:
        _ = action_dict_to_base_action(data)  # pyright: ignore [reportArgumentType]
    assert exc_info.value.errors()[0]["loc"] == ("value",)


def test_named_parameter_still_parses() -> None:
    action = action_dict_to_base_action({"type": "goto", "url": "https://example.com"})
    assert isinstance(action, GotoAction)
    assert action.url == "https://example.com"


def test_actions_whose_field_is_value_keep_it() -> None:
    fill = action_dict_to_base_action({"type": "fill", "id": "I1", "value": "hello"})
    assert isinstance(fill, FillAction)
    assert fill.value == "hello"
    form_fill = action_dict_to_base_action({"type": "form_fill", "value": {"email": "a@b.co"}})
    assert isinstance(form_fill, FormFillAction)
