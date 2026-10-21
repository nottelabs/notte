"""Tests to ensure action classes, TypedDicts, and session method overloads stay synchronized."""

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import get_args, get_origin, get_type_hints

import pytest
from notte_core.actions import typedicts as typedicts_module
from notte_core.actions.actions import BaseAction, BrowserAction
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


def _public_action_typedicts(hidden: frozenset[str]) -> set[str]:
    """TypedDicts of the actions that a session exposes (hidden actions only stay parseable)."""
    return {
        f"{action_cls.__name__}Dict"
        for action_type, action_cls in BaseAction.ACTION_REGISTRY.items()
        if action_type not in hidden
    }


# Local sessions can't run inbox reads; cloud sessions still run the API-side `email_verification_read`.
LOCAL_SESSION_HIDDEN_ACTIONS = BrowserAction.unlisted_action_types()
SDK_SESSION_HIDDEN_ACTIONS = (
    BrowserAction.LEGACY_AGENT_ACTION_TYPES
    | BrowserAction.PERSONA_INBOX_ACTION_TYPES
    | BrowserAction.RECORD_ONLY_ACTION_TYPES
)


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
    excluded_fields = {"accessible_name", "category", "description", "param", "press_enter", "text_label"}

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


GENERATOR = Path(__file__).parents[2] / "scripts" / "generate_action_overloads.py"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_action_overloads", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


generator = _load_generator()


def _overload_typedicts_in_file(path: Path, class_name: str, method: str) -> list[str]:
    """`XxxActionDict` names of the `**kwargs: Unpack[...]` overloads of `class_name.method`, in order."""
    tree = ast.parse(path.read_text())
    cls = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == class_name)
    names: list[str] = []
    for node in cls.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != method:
            continue
        if not any(isinstance(d, ast.Name) and d.id == "overload" for d in node.decorator_list):
            continue
        kwarg = node.args.kwarg
        if kwarg is not None and isinstance(kwarg.annotation, ast.Subscript):
            names.append(ast.unparse(kwarg.annotation.slice))
    return names


def test_generated_overloads_are_up_to_date() -> None:
    """The overload regions and TypedDict imports match `scripts/generate_action_overloads.py`."""
    stale = [
        str(path.relative_to(GENERATOR.parents[1]))
        for path in dict.fromkeys(target.path for target in generator.TARGETS)
        if generator.generate(path, path.read_text()) != path.read_text()
    ]
    assert not stale, f"Out of date, run `uv run --no-sync python scripts/generate_action_overloads.py`: {stale}"


@pytest.mark.parametrize(
    ("path", "class_name", "method", "hidden"),
    [
        (generator.LOCAL_SESSION, "NotteSession", "aexecute", LOCAL_SESSION_HIDDEN_ACTIONS),
        (generator.LOCAL_SESSION, "NotteSession", "execute", LOCAL_SESSION_HIDDEN_ACTIONS),
        (generator.REMOTE_SESSION, "RemoteSession", "execute", SDK_SESSION_HIDDEN_ACTIONS),
    ],
)
def test_execute_overloads_cover_exactly_the_exposed_actions(
    path: Path, class_name: str, method: str, hidden: frozenset[str]
) -> None:
    (target,) = [target for target in generator.TARGETS if (target.path, target.method) == (path, method)]
    assert target.hidden == hidden

    overloaded = _overload_typedicts_in_file(path, class_name, method)
    assert overloaded == generator.overload_typedicts(hidden)
    assert set(overloaded) == _public_action_typedicts(hidden)


def test_api_only_actions_are_typed_on_cloud_sessions_only() -> None:
    local = set(generator.overload_typedicts(LOCAL_SESSION_HIDDEN_ACTIONS))
    remote = set(generator.overload_typedicts(SDK_SESSION_HIDDEN_ACTIONS))
    assert remote - local == {"EmailVerificationReadActionDict"}
    for hidden in ("EmailReadActionDict", "SmsReadActionDict", "ScrapeActionDict", "HelpActionDict"):
        assert hidden not in local | remote
