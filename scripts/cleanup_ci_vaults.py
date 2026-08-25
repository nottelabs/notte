#!/usr/bin/env python3
"""Delete *orphaned* CI vaults for the configured NOTTE_API_KEY account.

Docs/integration tests create ephemeral vaults. Cancelled runs can leak them until
the account hits the active-vault limit (HTTP 429 on vaults/create).

This script is intentionally conservative so parallel CI jobs are not disrupted:
- Never deletes persona-owned vaults (unless --include-persona).
- Only deletes vaults whose names look ephemeral (default / pytest- / test- / ...).
- Only deletes vaults older than --min-age-hours (default: 2h).

Do not call this from every PR job with a short age window. Prefer proper
per-test teardown, and use this for manual/scheduled orphan drain.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from typing import Any

from notte_sdk import NotteClient

# Names produced by CI/docs snippets (VaultCreateRequest default is "default").
_EPHEMERAL_NAME_RE = re.compile(
    r"^(default|pytest-.+|test-.+|test_vault.*|test-code-sample-.+)$",
    re.IGNORECASE,
)


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


def _vault_created_at(vault: Any) -> dt.datetime | None:
    created_at = getattr(vault, "created_at", None)
    if created_at is None:
        return None
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=dt.timezone.utc)
    return created_at


def is_ephemeral_ci_vault(vault: Any, *, min_age: dt.timedelta, now: dt.datetime) -> bool:
    if bool(getattr(vault, "for_persona", False)):
        return False
    name = str(getattr(vault, "name", "") or "")
    if not _EPHEMERAL_NAME_RE.match(name):
        return False
    created_at = _vault_created_at(vault)
    if created_at is None:
        return False
    return (now - created_at) >= min_age


def cleanup_vaults(
    *,
    dry_run: bool,
    include_persona: bool,
    force: bool,
    min_age_hours: float,
    all_non_persona: bool,
) -> int:
    if not force and os.environ.get("CI", "").lower() not in {"1", "true", "yes"}:
        print(
            "Refusing to delete vaults outside CI. Re-run with --force if you really mean it.",
            file=sys.stderr,
        )
        return 2

    if min_age_hours < 0:
        print("--min-age-hours must be >= 0", file=sys.stderr)
        return 2

    client = NotteClient()
    vaults = list_active_vaults(client)
    now = dt.datetime.now(tz=dt.timezone.utc)
    min_age = dt.timedelta(hours=min_age_hours)

    if all_non_persona:
        targets = [vault for vault in vaults if include_persona or not bool(getattr(vault, "for_persona", False))]
        print(
            "WARNING: --all-non-persona deletes every matching vault regardless of name/age; unsafe with parallel CI."
        )
    else:
        targets = [
            vault
            for vault in vaults
            if (include_persona or not bool(getattr(vault, "for_persona", False)))
            and is_ephemeral_ci_vault(vault, min_age=min_age, now=now)
        ]

    print(
        f"Found {len(vaults)} active vault(s); deleting {len(targets)} orphan(s) "
        + f"(min_age_hours={min_age_hours}, all_non_persona={all_non_persona})."
    )
    if dry_run:
        for vault in targets:
            name = getattr(vault, "name", None)
            for_persona = getattr(vault, "for_persona", False)
            created_at = getattr(vault, "created_at", None)
            print(
                f"  [dry-run] would delete {vault.vault_id} "
                + f"name={name!r} for_persona={for_persona} created_at={created_at}"
            )
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
    remaining_orphans = [
        vault
        for vault in remaining
        if (include_persona or not bool(getattr(vault, "for_persona", False)))
        and is_ephemeral_ci_vault(vault, min_age=min_age, now=dt.datetime.now(tz=dt.timezone.utc))
    ]
    print(f"Done. deleted={deleted} failed={failed} remaining_orphan_candidates={len(remaining_orphans)}")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--dry-run", action="store_true", help="List vaults without deleting")
    _ = parser.add_argument(
        "--include-persona",
        action="store_true",
        help="Also consider persona-owned vaults (dangerous; default skips them)",
    )
    _ = parser.add_argument(
        "--force",
        action="store_true",
        help="Allow deletion outside CI (required for local manual cleanup)",
    )
    _ = parser.add_argument(
        "--min-age-hours",
        type=float,
        default=2.0,
        help="Only delete ephemeral-named vaults at least this old (default: 2)",
    )
    _ = parser.add_argument(
        "--all-non-persona",
        action="store_true",
        help="Delete all non-persona vaults (ignores name/age). Unsafe with parallel CI.",
    )
    args = parser.parse_args()
    return cleanup_vaults(
        dry_run=args.dry_run,
        include_persona=args.include_persona,
        force=args.force,
        min_age_hours=args.min_age_hours,
        all_non_persona=args.all_non_persona,
    )


if __name__ == "__main__":
    raise SystemExit(main())
