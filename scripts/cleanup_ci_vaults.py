#!/usr/bin/env python3
"""Delete leaked CI vaults for the configured NOTTE_API_KEY account.

Docs and integration tests create ephemeral vaults. If a job is cancelled or a
snippet exits without cleanup, vaults accumulate until the account hits the
active-vault limit (currently 1000) and CI fails with HTTP 429.

This script is a safety net: list every active non-persona vault and delete it.
Persona vaults are owned by personas and excluded by default.

Refuses to run outside CI unless --force is passed (protects personal vaults).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from notte_sdk import NotteClient


def list_active_vaults(client: NotteClient, *, page_size: int = 100) -> list[Any]:
    vaults: list[Any] = []
    page = 1
    while True:
        batch = list(client.vaults.list(page=page, page_size=page_size, only_active=True))
        if not batch:
            break
        vaults.extend(batch)
        if len(batch) < page_size:
            break
        page += 1
    return vaults


def cleanup_vaults(*, dry_run: bool, include_persona: bool, force: bool) -> int:
    if not force and os.environ.get("CI", "").lower() not in {"1", "true", "yes"}:
        print(
            "Refusing to delete vaults outside CI. Re-run with --force if you really mean it.",
            file=sys.stderr,
        )
        return 2

    client = NotteClient()
    vaults = list_active_vaults(client)
    targets = [vault for vault in vaults if include_persona or not bool(getattr(vault, "for_persona", False))]

    print(f"Found {len(vaults)} active vault(s); deleting {len(targets)}.")
    if dry_run:
        for vault in targets:
            name = getattr(vault, "name", None)
            for_persona = getattr(vault, "for_persona", False)
            print(f"  [dry-run] would delete {vault.vault_id} name={name!r} for_persona={for_persona}")
        return 0

    deleted = 0
    failed = 0
    for vault in targets:
        try:
            _ = client.vaults.delete(vault.vault_id)
            deleted += 1
            print(f"  deleted {vault.vault_id} name={getattr(vault, 'name', None)!r}")
        except Exception as exc:  # noqa: BLE001 - best-effort CI cleanup
            failed += 1
            print(f"  failed {vault.vault_id}: {exc}", file=sys.stderr)

    remaining = list_active_vaults(client)
    remaining_targets = [
        vault for vault in remaining if include_persona or not bool(getattr(vault, "for_persona", False))
    ]
    print(f"Done. deleted={deleted} failed={failed} remaining_non_persona={len(remaining_targets)}")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--dry-run", action="store_true", help="List vaults without deleting")
    _ = parser.add_argument(
        "--include-persona",
        action="store_true",
        help="Also delete persona-owned vaults (dangerous; default skips them)",
    )
    _ = parser.add_argument(
        "--force",
        action="store_true",
        help="Allow deletion outside CI (required for local manual cleanup)",
    )
    args = parser.parse_args()
    return cleanup_vaults(dry_run=args.dry_run, include_persona=args.include_persona, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
