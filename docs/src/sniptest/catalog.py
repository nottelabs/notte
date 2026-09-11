"""Source catalog for multi-tab snippets, including commands and sample output."""

import json
from pathlib import Path


def load_catalog(testers: Path) -> dict:
    path = testers / "snippets.json"
    return json.loads(path.read_text()) if path.exists() else {}


def source_path(testers: Path, source: str) -> Path:
    path = (testers / source).resolve()
    if not path.is_relative_to(testers.resolve()) or not path.is_file():
        raise ValueError(f"Missing or unsafe snippet source: {source}")
    return path


def catalog_sources(testers: Path) -> set[Path]:
    return {
        source_path(testers, block["source"]) for spec in load_catalog(testers).values() for block in spec["blocks"]
    }


def execution_backlog(testers: Path) -> dict[str, str]:
    return {
        block["source"]: block["execution_pending"]
        for spec in load_catalog(testers).values()
        for block in spec["blocks"]
        if block.get("execution_pending")
    }


def check_catalog_migration(current: dict, previous: dict) -> list[str]:
    """Legacy exemptions can shrink, but cannot exempt new scripts from pairing/tests."""
    old = {block["source"]: block for spec in previous.values() for block in spec["blocks"]}
    new = {block["source"]: block for spec in current.values() for block in spec["blocks"]}
    errors = []
    for source, block in new.items():
        for status in ("execution_pending", "existing_python_test"):
            if block.get(status) and not old.get(source, {}).get(status):
                errors.append(f"Legacy {status} exemption cannot grow: {source}")
        if source not in old and Path(source).suffix in (".py", ".ts"):
            suffix = ".ts" if source.endswith(".py") else ".py"
            if str(Path(source).with_suffix(suffix)) not in new:
                errors.append(f"New catalog script needs a same-name counterpart: {source}")
    return errors
