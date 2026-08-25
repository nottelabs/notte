#!/usr/bin/env python3
"""CLI to delete vaults owned by a single CI workflow run.

Preferred usage (from a workflow ``if: always()`` step)::

    NOTTE_CI_VAULT_PREFIX=ci-$GITHUB_RUN_ID-$GITHUB_JOB \\
      python scripts/cleanup_ci_vaults.py

Only vaults created under that prefix / recorded by ``ci_vault_scope.install()``
are deleted — parallel jobs sharing the same API key are left alone.

One-shot backlog drain (manual only)::

    python scripts/cleanup_ci_vaults.py --orphan-defaults --min-age-hours 2
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def _load_scope() -> object:
    path = Path(__file__).resolve().parent / "ci_vault_scope.py"
    spec = importlib.util.spec_from_file_location("ci_vault_scope", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--prefix",
        default=None,
        help="Vault name prefix for this run (default: $NOTTE_CI_VAULT_PREFIX)",
    )
    _ = parser.add_argument("--dry-run", action="store_true", help="List vaults without deleting")
    _ = parser.add_argument(
        "--orphan-defaults",
        action="store_true",
        help="One-shot: delete name=default vaults older than --min-age-hours (backlog drain)",
    )
    _ = parser.add_argument(
        "--min-age-hours",
        type=float,
        default=2.0,
        help="Age cutoff for --orphan-defaults (default: 2)",
    )
    args = parser.parse_args()

    scope = _load_scope()
    if args.orphan_defaults:
        cleanup_orphans = getattr(scope, "cleanup_orphan_defaults")
        return int(cleanup_orphans(dry_run=args.dry_run, min_age_hours=args.min_age_hours))

    cleanup = getattr(scope, "cleanup_this_run")
    return int(cleanup(dry_run=args.dry_run, prefix=args.prefix))


if __name__ == "__main__":
    raise SystemExit(main())
