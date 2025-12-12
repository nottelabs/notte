"""Tests to ensure action classes, TypedDicts, and session method overloads stay synchronized."""

import re
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

from notte_core.actions import typedicts as typedicts_module
from notte_core.actions.actions import BaseAction
from notte_core.actions.typedicts import ActionType


def _get_action_to_typeddict_mapping() -> dict[str, tuple[type[BaseAction], type]]:
    """
    Build a mapping from action type names to (ActionClass, TypedDictClass) tuples.

    Returns:
        dict mapping action type name (e.g., "goto") to (GotoAction, GotoActionDict)
    """
    mapping: dict[str, tuple[type[BaseAction], type]] = {}

    for action_type, action_cls in BaseAction.ACTION_REGISTRY.items():
        # TypedDict naming convention: {ActionClassName}Dict
        typeddict_name = f"{action_cls.__name__}Dict"
        typeddict_cls = getattr(typedicts_module, typeddict_name, None)

        if typeddict_cls is not None:
            mapping[action_type] = (action_cls, typeddict_cls)

    return mapping


def test_all_actions_have_typeddict() -> None:
    """Test that every action in ACTION_REGISTRY has a corresponding TypedDict."""
    missing_typedicts: list[str] = []

    for _action_type, action_cls in BaseAction.ACTION_REGISTRY.items():
        typeddict_name = f"{action_cls.__name__}Dict"
        typeddict_cls = getattr(typedicts_module, typeddict_name, None)

        if typeddict_cls is None:
            missing_typedicts.append(f"{action_cls.__name__} (expected {typeddict_name})")

    if missing_typedicts:
        raise AssertionError("Missing TypedDicts for actions:\n  - " + "\n  - ".join(missing_typedicts))


def test_action_type_literal_includes_all_actions() -> None:
    """Test that ActionType Literal includes all action types from ACTION_REGISTRY."""
    # Get all types from the ActionType Literal
    action_type_values = set(get_args(ActionType))

    # Get all action types from the registry
    registry_types = set(BaseAction.ACTION_REGISTRY.keys())

    # Check for missing types in ActionType
    missing_in_literal = registry_types - action_type_values
    if missing_in_literal:
        raise AssertionError(
            "ActionType Literal is missing these action types:\n  - " + "\n  - ".join(sorted(missing_in_literal))
        )

    # Check for extra types in ActionType (not in registry)
    extra_in_literal = action_type_values - registry_types
    if extra_in_literal:
        raise AssertionError(
            "ActionType Literal has extra types not in ACTION_REGISTRY:\n  - " + "\n  - ".join(sorted(extra_in_literal))
        )


def test_typeddict_fields_match_action_fields() -> None:
    """Test that TypedDict fields match the corresponding action class fields."""
    # Fields that are excluded from TypedDicts (internal/metadata fields)
    excluded_fields = {"category", "description", "param", "press_enter", "text_label"}

    errors: list[str] = []
    mapping = _get_action_to_typeddict_mapping()

    for _action_type, (action_cls, typeddict_cls) in mapping.items():
        # Get fields from action class (Pydantic model)
        action_fields = set(action_cls.model_fields.keys()) - excluded_fields

        # Get fields from TypedDict
        typeddict_hints = get_type_hints(typeddict_cls)
        typeddict_fields = set(typeddict_hints.keys())

        # Check for missing fields in TypedDict
        missing_in_typeddict = action_fields - typeddict_fields
        if missing_in_typeddict:
            errors.append(
                f"{typeddict_cls.__name__} is missing fields from {action_cls.__name__}: {missing_in_typeddict}"
            )

        # Check for extra fields in TypedDict (not in action)
        extra_in_typeddict = typeddict_fields - action_fields
        if extra_in_typeddict:
            errors.append(
                f"{typeddict_cls.__name__} has extra fields not in {action_cls.__name__}: {extra_in_typeddict}"
            )

    if errors:
        raise AssertionError("Field mismatches between actions and TypedDicts:\n  - " + "\n  - ".join(errors))


def test_typeddict_type_field_matches_action_type() -> None:
    """Test that each TypedDict's 'type' field Literal matches the action's type."""
    errors: list[str] = []
    mapping = _get_action_to_typeddict_mapping()

    for action_type, (_action_cls, typeddict_cls) in mapping.items():
        typeddict_hints = get_type_hints(typeddict_cls)

        if "type" not in typeddict_hints:
            errors.append(f"{typeddict_cls.__name__} is missing 'type' field")
            continue

        type_hint = typeddict_hints["type"]

        # Extract Literal value(s) - handle Required[Literal[...]] wrapper
        literal_values: set[str] = set()
        if type_hint is type(None):
            continue

        # Unwrap Required/NotRequired if present
        origin = get_origin(type_hint)
        if origin is not None and hasattr(origin, "__name__") and origin.__name__ in ("Required", "NotRequired"):
            type_hint = get_args(type_hint)[0]

        # Now extract Literal values
        type_args = get_args(type_hint)
        if type_args:
            literal_values = set(type_args)
        else:
            # Direct Literal without wrapper
            literal_values = {type_hint} if isinstance(type_hint, str) else set()

        if action_type not in literal_values:
            errors.append(
                f"{typeddict_cls.__name__} type field Literal={literal_values} "
                f"doesn't match action type '{action_type}'"
            )

    if errors:
        raise AssertionError("Type field mismatches:\n  - " + "\n  - ".join(errors))


def _extract_overload_typedicts_from_file(file_path: Path, method_name: str) -> set[str]:
    """
    Extract TypedDict names used in @overload signatures for a specific method.

    Args:
        file_path: Path to the Python file
        method_name: Name of the method to check (e.g., 'execute', 'aexecute')

    Returns:
        Set of TypedDict names found in Unpack[XxxActionDict] patterns
    """
    content = file_path.read_text()

    # Pattern to find @overload decorated methods with Unpack[XxxActionDict]
    # This captures the TypedDict name from patterns like:
    # @overload
    # def execute(..., **kwargs: Unpack[GotoActionDict]) -> ...
    # or
    # async def aexecute(..., **kwargs: Unpack[GotoActionDict]) -> ...
    pattern = rf"@overload\s+(?:async\s+)?def\s+{method_name}\s*\([^)]*Unpack\[(\w+ActionDict)\][^)]*\)"

    matches = re.findall(pattern, content)
    return set(matches)


def test_browser_session_execute_overloads_present() -> None:
    """Test that notte_browser/session.py has execute overloads for all TypedDicts."""
    session_file = (
        Path(__file__).parent.parent.parent / "packages" / "notte-browser" / "src" / "notte_browser" / "session.py"
    )

    assert session_file.exists(), f"Session file not found: {session_file}"

    overloaded_typedicts = _extract_overload_typedicts_from_file(session_file, "execute")

    # Get all expected TypedDicts
    expected_typedicts = {f"{action_cls.__name__}Dict" for action_cls in BaseAction.ACTION_REGISTRY.values()}

    missing = expected_typedicts - overloaded_typedicts
    if missing:
        raise AssertionError(
            "notte_browser/session.py execute() is missing overloads for:\n  - " + "\n  - ".join(sorted(missing))
        )


def test_browser_session_aexecute_overloads_present() -> None:
    """Test that notte_browser/session.py has aexecute overloads for all TypedDicts."""
    session_file = (
        Path(__file__).parent.parent.parent / "packages" / "notte-browser" / "src" / "notte_browser" / "session.py"
    )

    assert session_file.exists(), f"Session file not found: {session_file}"

    overloaded_typedicts = _extract_overload_typedicts_from_file(session_file, "aexecute")

    # Get all expected TypedDicts
    expected_typedicts = {f"{action_cls.__name__}Dict" for action_cls in BaseAction.ACTION_REGISTRY.values()}

    missing = expected_typedicts - overloaded_typedicts
    if missing:
        raise AssertionError(
            "notte_browser/session.py aexecute() is missing overloads for:\n  - " + "\n  - ".join(sorted(missing))
        )


def test_sdk_session_execute_overloads_present() -> None:
    """Test that notte_sdk/endpoints/sessions.py has execute overloads for all TypedDicts."""
    sessions_file = (
        Path(__file__).parent.parent.parent
        / "packages"
        / "notte-sdk"
        / "src"
        / "notte_sdk"
        / "endpoints"
        / "sessions.py"
    )

    assert sessions_file.exists(), f"Sessions file not found: {sessions_file}"

    overloaded_typedicts = _extract_overload_typedicts_from_file(sessions_file, "execute")

    # Get all expected TypedDicts
    expected_typedicts = {f"{action_cls.__name__}Dict" for action_cls in BaseAction.ACTION_REGISTRY.values()}

    missing = expected_typedicts - overloaded_typedicts
    if missing:
        raise AssertionError(
            "notte_sdk/endpoints/sessions.py execute() is missing overloads for:\n  - " + "\n  - ".join(sorted(missing))
        )
