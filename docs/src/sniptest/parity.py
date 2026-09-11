"""Enforce same-name SDK examples while allowing an explicit, shrinking backlog."""

import argparse
import json
import subprocess
from pathlib import Path

from catalog import catalog_sources, check_catalog_migration, execution_backlog, load_catalog

ROOT = Path(__file__).resolve().parents[3]
TESTERS = ROOT / "docs/src/testers"
MANIFEST = ROOT / "docs/src/sniptest/parity.json"


def check_parity(testers: Path, manifest: dict, previous: dict | None = None) -> list[str]:
    managed = catalog_sources(testers)
    python = {str(path.relative_to(testers)) for path in testers.rglob("*.py") if path.resolve() not in managed}
    typescript = {
        str(path.relative_to(testers).with_suffix(".py"))
        for path in testers.rglob("*.ts")
        if path.resolve() not in managed
    }
    backlog = set(manifest["unpaired"])
    exceptions = manifest["python_only"]
    allowed = backlog | set(exceptions)
    errors = []
    for name in sorted(python - typescript - allowed):
        errors.append(f"Missing TypeScript counterpart: {name}")
    for name in sorted(typescript - python):
        errors.append(f"Missing Python counterpart: {Path(name).with_suffix('.ts')}")
    for name in sorted(allowed - (python - typescript)):
        errors.append(f"Remove stale backlog/exception entry: {name}")
    if len(backlog) != len(manifest["unpaired"]) or backlog & set(exceptions):
        errors.append("Duplicate backlog/exception entries")
    for name, reason in exceptions.items():
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"Python-only exception needs a reason: {name}")
    if previous is not None:
        for name in sorted(backlog - set(previous["unpaired"])):
            errors.append(f"Migration backlog cannot grow: {name}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", help="Compare backlog against a trusted git base reference")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    previous = None
    if args.base_ref:
        catalog_result = subprocess.run(
            ["git", "show", f"{args.base_ref}:docs/src/testers/snippets.json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        catalog = load_catalog(TESTERS)
        if catalog_result.returncode == 0:
            old_catalog = json.loads(catalog_result.stdout)
            errors = check_catalog_migration(catalog, old_catalog)
            if errors:
                raise SystemExit("\n".join(errors))
        else:
            # Initial extraction may only register snippets that were already manually maintained.
            for target in catalog:
                old = subprocess.run(
                    ["git", "show", f"{args.base_ref}:docs/src/snippets/{target}"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                )
                if old.returncode or "Auto-generated mdx file" in old.stdout:
                    raise SystemExit(f"Not a legacy manual snippet in the base: {target}")
        result = subprocess.run(
            ["git", "show", f"{args.base_ref}:docs/src/sniptest/parity.json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        # Bootstrap only when the reference exists and the manifest has not landed yet.
        if result.returncode:
            subprocess.run(["git", "rev-parse", "--verify", args.base_ref], cwd=ROOT, check=True, capture_output=True)
            # Missing manifests are allowed only for the initial migration, not arbitrary git failures.
            exists = subprocess.run(
                ["git", "ls-tree", "--name-only", args.base_ref, "docs/src/sniptest/parity.json"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            if exists.stdout.strip():
                raise RuntimeError(result.stderr)
            # Only pre-existing Python examples can enter the initial backlog.
            files = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", args.base_ref, "docs/src/testers"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            previous = {
                "unpaired": [
                    p.removeprefix("docs/src/testers/") for p in files.stdout.splitlines() if p.endswith(".py")
                ]
            }
        else:
            previous = json.loads(result.stdout)
    errors = check_parity(TESTERS, manifest, previous)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"SDK example parity OK; {len(manifest['unpaired'])} examples remain in the migration backlog")
    if load_catalog(TESTERS):
        print(
            f"Legacy source catalog: {len(load_catalog(TESTERS))} snippets, {len(execution_backlog(TESTERS))} scripts awaiting execution fixtures (not live-tested)"
        )
        python = {p.relative_to(TESTERS).with_suffix("") for p in TESTERS.rglob("*.py")}
        typescript = {p.relative_to(TESTERS).with_suffix("") for p in TESTERS.rglob("*.ts")}
        print(
            f"Total source coverage: {len(python)} Python, {len(typescript)} TypeScript, {len(python & typescript)} same-name pairs; {len(python - typescript)} Python sources still lack a TypeScript counterpart"
        )


if __name__ == "__main__":
    main()
