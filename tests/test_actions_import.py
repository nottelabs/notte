# Import the SDK actions module
from typing import Any

import notte_sdk.actions as sdk_actions
from notte_core.actions import BaseAction


def test_actions_registry_matches_sdk_imports():
    """Test that all actions from notte_core registry are imported in notte_sdk."""
    # Get all action classes from the core registry
    core_action_classes = set(BaseAction.ACTION_REGISTRY.values())

    # Get all action classes from SDK imports
    sdk_action_classes = set()
    for action_name in sdk_actions.__all__:
        action_class = getattr(sdk_actions, action_name)
        sdk_action_classes.add(action_class)

    # Find differences by comparing the actual classes
    missing_in_sdk = core_action_classes - sdk_action_classes
    extra_in_sdk = sdk_action_classes - core_action_classes

    # Report any differences
    error_messages: list[str] = []
    if missing_in_sdk:
        missing_names = [cls.__name__ for cls in missing_in_sdk]
        error_messages.append(f"Action classes in core registry but missing from SDK: {sorted(missing_names)}")
    if extra_in_sdk:
        extra_names: list[Any] = [cls.__name__ for cls in extra_in_sdk]
        error_messages.append(f"Action classes in SDK but not in core registry: {sorted(extra_names)}")

    assert not error_messages, "\n".join(error_messages)
