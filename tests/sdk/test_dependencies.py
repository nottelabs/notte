"""notte-sdk declares the third-party packages it imports itself."""

import re
import tomllib
from pathlib import Path

SDK = Path(__file__).resolve().parents[2] / "packages/notte-sdk"


def _declared_dependencies() -> set[str]:
    project = tomllib.loads((SDK / "pyproject.toml").read_text())["project"]
    return {re.split(r"[\s<>=!~;\[]", requirement, maxsplit=1)[0].lower() for requirement in project["dependencies"]}


def test_anyio_is_declared() -> None:
    # The transport and retry code import anyio directly. httpx usually brings it, but not every httpx build
    # does (Pyodide's has no dependencies), so the SDK must not rely on it arriving transitively.
    importers = [path for path in (SDK / "src").rglob("*.py") if re.search(r"^import anyio$", path.read_text(), re.M)]
    assert importers
    assert "anyio" in _declared_dependencies()
