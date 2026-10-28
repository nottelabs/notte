import subprocess
import sys
from pathlib import Path

import pytest

CONFTEST = Path(__file__).parent / "conftest.py"
# runs the conftest on its own, with notte_browser importable or not (`None` in sys.modules blocks the import)
SCRIPT = """
import runpy, sys
if sys.argv[1] == "blocked":
    sys.modules["notte_browser"] = None
print(runpy.run_path(sys.argv[2])["pytest_plugins"])
"""


@pytest.mark.parametrize(
    ("notte_browser", "plugins"), [("installed", "['tests.flake_diagnostics']"), ("blocked", "[]")]
)
def test_flake_diagnostics_load_only_with_notte_browser(notte_browser: str, plugins: str) -> None:
    # SDK-only environments (the websocket compatibility check) have no notte_browser for the plugin to import
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, notte_browser, str(CONFTEST)],
        capture_output=True,
        text=True,
        check=True,
        cwd=CONFTEST.parent.parent,
    )
    assert result.stdout.strip().splitlines()[-1] == plugins
