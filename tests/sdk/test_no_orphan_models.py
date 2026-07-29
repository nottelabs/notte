import inspect
import re
from pathlib import Path

import notte_sdk
from notte_sdk import types as types_module
from notte_sdk.types import SdkRequest, SdkResponse

SDK_SRC = Path(inspect.getfile(notte_sdk)).parent

# Models intentionally defined but referenced nowhere else in the SDK.
# Every entry needs a written reason. This dict should stay empty.
ALLOWED_UNREFERENCED: dict[str, str] = {}


def test_every_model_is_referenced_somewhere() -> None:
    """Every SdkRequest/SdkResponse in types.py must be referenced outside its own class definition.

    A model whose name appears exactly once in the SDK source (its `class X(...)` line)
    is wired to nothing: no endpoint builds it, no other model embeds it. Wire it,
    delete it, or add it to ALLOWED_UNREFERENCED with a reason.
    """
    models = {
        name
        for name, obj in vars(types_module).items()
        if inspect.isclass(obj)
        and issubclass(obj, (SdkRequest, SdkResponse))
        and obj not in (SdkRequest, SdkResponse)
        and obj.__module__ == types_module.__name__
    }
    code = "\n".join(p.read_text() for p in sorted(SDK_SRC.rglob("*.py")))
    orphans = {
        name for name in models if len(re.findall(rf"\b{name}\b", code)) <= 1 and name not in ALLOWED_UNREFERENCED
    }
    assert not orphans, (
        f"Models defined in notte_sdk/types.py but referenced nowhere else in the SDK: {sorted(orphans)}. "
        "Wire each to an endpoint, delete it, or add it to ALLOWED_UNREFERENCED with a reason."
    )


def test_allowlist_entries_are_still_orphans() -> None:
    """Entries in ALLOWED_UNREFERENCED must be removed once the model gains a real reference."""
    code = "\n".join(p.read_text() for p in sorted(SDK_SRC.rglob("*.py")))
    stale = {name for name in ALLOWED_UNREFERENCED if len(re.findall(rf"\b{name}\b", code)) > 1}
    assert not stale, f"Now referenced, remove from ALLOWED_UNREFERENCED: {sorted(stale)}"
