"""The public types modules export types, not the modules and helpers they import."""

import types
from pathlib import Path, PurePath

import notte_core.types
import notte_sdk.types

LEAKED_NAMES = ("os", "json", "re", "warnings", "dt", "Path", "PurePath", "TOTP")


def _is_module_or_path(value: object) -> bool:
    return isinstance(value, types.ModuleType) or value in (Path, PurePath)


def test_core_types_all_lists_no_module_or_path() -> None:
    exported = {name: getattr(notte_core.types, name) for name in notte_core.types.__all__}
    assert [name for name, value in exported.items() if _is_module_or_path(value)] == []
    assert [name for name in LEAKED_NAMES if name in exported] == []


def test_sdk_types_has_no_module_or_path() -> None:
    public = {k: v for k, v in vars(notte_sdk.types).items() if not k.startswith("_")}
    assert [name for name, value in public.items() if _is_module_or_path(value)] == []
    assert [name for name in LEAKED_NAMES if name in public] == []


def test_sdk_types_keeps_core_public_names() -> None:
    assert [name for name in notte_core.types.__all__ if not hasattr(notte_sdk.types, name)] == []
