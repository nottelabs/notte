"""Everything under tests/integration needs the network, so it is kept out of the offline unit gate.

- tests/integration/sdk/** talks to the Notte API (NOTTE_API_KEY, NOTTE_API_URL): marked `staging`.
- every other test here drives a local browser against third-party websites: marked `live`.

Markers are added by path, so a new test dropped in here is excluded from `make test` without anyone
remembering to mark it. Tests elsewhere that need the network carry an explicit `live`/`staging` mark.
See the `markers` list in pyproject.toml and the `test*` targets in the makefile.
"""

from pathlib import Path

import pytest

_INTEGRATION_DIR = Path(__file__).parent
_SDK_DIR = _INTEGRATION_DIR / "sdk"


# tryfirst: `-m` deselection is itself a pytest_collection_modifyitems hook, so the markers must be
# in place before it runs. The hook sees every collected item, hence the path filter.
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = item.path
        if not path.is_relative_to(_INTEGRATION_DIR):
            continue
        _ = item.add_marker(pytest.mark.staging if path.is_relative_to(_SDK_DIR) else pytest.mark.live)
