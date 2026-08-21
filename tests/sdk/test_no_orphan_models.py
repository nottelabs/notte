import inspect
import re
from pathlib import Path

import notte_sdk
from notte_sdk import types as types_module
from notte_sdk.types import SdkRequest, SdkResponse

SDK_SRC = Path(inspect.getfile(notte_sdk)).parent

# Models intentionally retained as import-compatible legacy API types.
ALLOWED_UNREFERENCED: dict[str, str] = {
    "DownloadFileRequest": "Deprecated global-storage request retained for import compatibility",
    "FileUploadResponse": "Deprecated global-storage response retained for import compatibility",
    "ListFilesResponse": "Deprecated global-storage response retained for import compatibility",
}


def _models() -> set[str]:
    return {
        name
        for name, obj in vars(types_module).items()
        if inspect.isclass(obj)
        and issubclass(obj, (SdkRequest, SdkResponse))
        and obj not in (SdkRequest, SdkResponse)
        and obj.__module__ == types_module.__name__
    }


def _sdk_code() -> str:
    """SDK source with per-line comments stripped, so commented-out code never counts as a reference."""
    lines: list[str] = []
    for path in sorted(SDK_SRC.rglob("*.py")):
        lines.extend(line.split("#", 1)[0] for line in path.read_text().splitlines())
    return "\n".join(lines)


def _reference_count(name: str, code: str) -> int:
    return len(re.findall(rf"\b{name}\b", code))


def test_every_model_is_referenced_somewhere() -> None:
    """Every SdkRequest/SdkResponse in types.py must be referenced outside its own class definition.

    A model whose name appears exactly once in the SDK source (its `class X(...)` line)
    is wired to nothing: no endpoint builds it, no other model embeds it. Wire it,
    delete it, or add it to ALLOWED_UNREFERENCED with a reason.
    """
    code = _sdk_code()
    orphans = {name for name in _models() if _reference_count(name, code) <= 1 and name not in ALLOWED_UNREFERENCED}
    assert not orphans, (
        f"Models defined in notte_sdk/types.py but referenced nowhere else in the SDK: {sorted(orphans)}. "
        "Wire each to an endpoint, delete it, or add it to ALLOWED_UNREFERENCED with a reason."
    )


def test_allowlist_is_valid_and_not_stale() -> None:
    """ALLOWED_UNREFERENCED entries must name existing models, carry a reason, and still be orphans."""
    models = _models()
    unknown = set(ALLOWED_UNREFERENCED) - models
    assert not unknown, (
        f"Not models in types.py (deleted or renamed?), remove from ALLOWED_UNREFERENCED: {sorted(unknown)}"
    )

    missing_reason = {name for name, reason in ALLOWED_UNREFERENCED.items() if not reason.strip()}
    assert not missing_reason, f"Empty reasons in ALLOWED_UNREFERENCED: {sorted(missing_reason)}"

    code = _sdk_code()
    stale = {name for name in ALLOWED_UNREFERENCED if _reference_count(name, code) > 1}
    assert not stale, f"Now referenced, remove from ALLOWED_UNREFERENCED: {sorted(stale)}"
