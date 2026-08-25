"""Docs snippet test hooks.

Installs CI vault scoping when ``NOTTE_CI_VAULT_PREFIX`` is set so this workflow
run names vaults under that prefix. Deletion is done by the workflow
``Cleanup vaults created by this run`` step (not here) so pytest-xdist workers
cannot delete vaults still in use by sibling workers.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any


def _load_ci_vault_scope() -> Any | None:
    if not os.environ.get("NOTTE_CI_VAULT_PREFIX"):
        return None
    path = Path(__file__).resolve().parents[2] / "scripts" / "ci_vault_scope.py"
    spec = importlib.util.spec_from_file_location("ci_vault_scope", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules["ci_vault_scope"] = module
    spec.loader.exec_module(module)
    return module


_SCOPE = _load_ci_vault_scope()
if _SCOPE is not None:
    _SCOPE.install()
