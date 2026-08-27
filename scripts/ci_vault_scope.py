#!/usr/bin/env python3
"""Scope vault creates to the current CI workflow run and delete only those.

When ``NOTTE_CI_VAULT_PREFIX`` is set (e.g. ``ci-<run_id>-<job>``):
1. ``install()`` patches ``VaultsClient.create`` so unnamed/default vaults get a
   unique name under that prefix and their IDs are recorded.
2. ``cleanup_this_run()`` deletes only vaults created under that prefix / recorded
   for this run — never other parallel jobs' vaults.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

_VAULT_NAME_RE = re.compile(r"^[a-zA-Z0-9\s\-_]+$")
_installed = False


def sanitize_prefix(raw: str) -> str:
    """Make a vault-name-safe prefix (API: 3-50 chars, [A-Za-z0-9 _-])."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw.strip()).strip("-_")
    # Leave room for "-xxxxxxxx" suffix (9 chars); API max name length is 50.
    cleaned = cleaned[:41].rstrip("-_")
    if len(cleaned) < 3:
        cleaned = f"ci-{cleaned}" if cleaned else "ci-run"
    return cleaned


def run_prefix() -> str | None:
    raw = os.environ.get("NOTTE_CI_VAULT_PREFIX", "").strip()
    if not raw:
        return None
    return sanitize_prefix(raw)


def _ids_file(prefix: str) -> Path:
    base = Path(os.environ.get("RUNNER_TEMP") or os.environ.get("TMPDIR") or "/tmp")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", prefix)
    return base / f"notte-ci-vault-ids-{safe}.txt"


def record_vault_id(prefix: str, vault_id: str) -> None:
    path = _ids_file(prefix)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Append is atomic enough per line on POSIX for concurrent xdist workers.
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(f"{vault_id}\n")
        handle.flush()
        os.fsync(handle.fileno())


def recorded_vault_ids(prefix: str) -> list[str]:
    path = _ids_file(prefix)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def install() -> None:
    """Patch vault create so this CI run owns a unique name prefix."""
    global _installed
    prefix = run_prefix()
    if prefix is None or _installed:
        return

    from notte_sdk.endpoints.vaults import VaultsClient

    original_create = VaultsClient.create

    def create(self: Any, **data: Any) -> Any:
        name = data.get("name")
        if name is None or name == "default":
            candidate = f"{prefix}-{uuid4().hex[:8]}"
            if not _VAULT_NAME_RE.match(candidate):
                candidate = re.sub(r"[^a-zA-Z0-9_-]+", "-", candidate)
            data = {**data, "name": candidate}
        vault = original_create(self, **data)
        vault_id = getattr(vault, "vault_id", None)
        if isinstance(vault_id, str) and vault_id:
            record_vault_id(prefix, vault_id)
        return vault

    VaultsClient.create = create
    _installed = True
    print(f"[ci-vault-scope] installed create patch prefix={prefix!r}", file=sys.stderr)


def list_active_vaults(client: Any, *, page_size: int = 100) -> list[Any]:
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


def cleanup_this_run(*, dry_run: bool = False, prefix: str | None = None) -> int:
    """Delete only vaults created by this workflow run (prefix + recorded IDs)."""
    resolved = sanitize_prefix(prefix) if prefix else run_prefix()
    if resolved is None:
        print("No NOTTE_CI_VAULT_PREFIX / --prefix; nothing to clean.", file=sys.stderr)
        return 0

    from notte_sdk import NotteClient

    client = NotteClient()
    recorded = set(recorded_vault_ids(resolved))
    listed = list_active_vaults(client)
    by_prefix = {
        vault.vault_id
        for vault in listed
        if str(getattr(vault, "name", "") or "").startswith(resolved) and not bool(getattr(vault, "for_persona", False))
    }
    targets = sorted(recorded | by_prefix)

    print(
        f"[ci-vault-scope] prefix={resolved!r} recorded={len(recorded)} "
        + f"by_prefix={len(by_prefix)} deleting={len(targets)} dry_run={dry_run}"
    )
    if dry_run:
        for vault_id in targets:
            print(f"  [dry-run] would delete {vault_id}")
        return 0

    deleted = 0
    failed = 0
    already_gone = 0
    for vault_id in targets:
        try:
            _ = client.vaults.delete(vault_id)
            deleted += 1
            print(f"  deleted {vault_id}")
        except Exception as exc:  # noqa: BLE001 - best-effort run teardown
            if _is_already_deleted_error(exc):
                already_gone += 1
                print(f"  already gone {vault_id}")
                continue
            failed += 1
            print(f"  failed {vault_id}: {exc}", file=sys.stderr)

    print(f"[ci-vault-scope] done deleted={deleted} already_gone={already_gone} failed={failed}")
    return 0 if failed == 0 else 1


def _is_already_deleted_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "not active" in text or "not found" in text or ("already" in text and "deleted" in text)


def cleanup_orphan_defaults(*, dry_run: bool, min_age_hours: float) -> int:
    """One-shot drain of leaked name=default vaults older than min_age_hours."""
    import datetime as dt

    from notte_sdk import NotteClient

    if min_age_hours < 0:
        print("--min-age-hours must be >= 0", file=sys.stderr)
        return 2

    client = NotteClient()
    now = dt.datetime.now(tz=dt.timezone.utc)
    min_age = dt.timedelta(hours=min_age_hours)
    targets: list[Any] = []
    for vault in list_active_vaults(client):
        if bool(getattr(vault, "for_persona", False)):
            continue
        if str(getattr(vault, "name", "") or "") != "default":
            continue
        created_at = getattr(vault, "created_at", None)
        if created_at is None:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=dt.timezone.utc)
        if (now - created_at) < min_age:
            continue
        targets.append(vault)

    print(f"[ci-vault-scope] orphan default vaults older than {min_age_hours}h: {len(targets)}")
    if dry_run:
        for vault in targets:
            print(f"  [dry-run] would delete {vault.vault_id} created_at={vault.created_at}")
        return 0

    deleted = 0
    failed = 0
    already_gone = 0
    for vault in targets:
        try:
            _ = client.vaults.delete(vault.vault_id)
            deleted += 1
            print(f"  deleted {vault.vault_id}")
        except Exception as exc:  # noqa: BLE001
            if _is_already_deleted_error(exc):
                already_gone += 1
                print(f"  already gone {vault.vault_id}")
                continue
            failed += 1
            print(f"  failed {vault.vault_id}: {exc}", file=sys.stderr)
    print(f"[ci-vault-scope] orphan drain done deleted={deleted} already_gone={already_gone} failed={failed}")
    return 0 if failed == 0 else 1
