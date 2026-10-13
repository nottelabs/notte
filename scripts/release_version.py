"""Validate Python release tags and advance the workspace development version."""

import argparse
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STABLE = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"


def release_version(tag: str) -> str:
    version = tag.removeprefix("v")
    if not re.fullmatch(STABLE, version):
        raise ValueError(f"Expected a stable X.Y.Z or vX.Y.Z tag, got {tag!r}")
    return version


def workspace(root: Path) -> tuple[str, dict[Path, str]]:
    files = [root / "pyproject.toml", *sorted((root / "packages").glob("*/pyproject.toml"))]
    texts = {path: path.read_text() for path in files}
    versions = {path: tomllib.loads(text)["project"]["version"] for path, text in texts.items()}
    current = versions[files[0]]
    for path, version in versions.items():
        if version != current:
            raise ValueError(f"{path}: version {version!r} does not match root version {current!r}")
    # Validate internal pins too, including optional dependencies and underscore names.
    for path, text in texts.items():
        for pin in re.findall(r'["\']notte[-_][A-Za-z0-9_-]+==([^"\']+)["\']', text):
            if pin != current:
                raise ValueError(f"{path}: internal dependency version {pin!r} does not match {current!r}")
    return current, texts


def update(texts: dict[Path, str], current: str, target: str) -> None:
    for path, text in texts.items():
        text = re.sub(
            r'(?m)^(version\s*=\s*["\'])' + re.escape(current) + r'(["\'])',
            lambda match: match[1] + target + match[2],
            text,
        )
        text = re.sub(
            r'(["\']notte[-_][A-Za-z0-9_-]+==)' + re.escape(current) + r'(["\'])',
            lambda match: match[1] + target + match[2],
            text,
        )
        _ = path.write_text(text)


def run(command: str, tag: str, root: Path = ROOT) -> None:
    version = release_version(tag)
    current, texts = workspace(root)
    if command in ("validate", "release"):
        if current not in (version, f"{version}.dev", f"{version}.dev0"):
            raise ValueError(f"Release tag {tag!r} does not match workspace version {current!r}")
        if command == "release":
            update(texts, current, version)
    else:
        major, minor, patch = map(int, version.split("."))
        target = f"{major}.{minor}.{patch + 1}.dev0"
        match = re.fullmatch(STABLE + r"(?:\.dev0?)?", current)
        if match is None:
            raise ValueError(f"Unsupported workspace version {current!r}")
        if tuple(map(int, match.groups())) > (major, minor, patch):
            print(f"Workspace already advanced to {current}; nothing to do.")
            return
        if current not in (version, f"{version}.dev", f"{version}.dev0"):
            raise ValueError(f"Workspace {current!r} is behind release {tag!r}; refusing an automatic bump")
        update(texts, current, target)
        print(f"Advanced workspace to {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("command", choices=("validate", "release", "next"))
    _ = parser.add_argument("tag")
    args = parser.parse_args()
    try:
        run(args.command, args.tag)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
