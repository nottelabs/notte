"""Build a local release while preserving the checkout's manifests and lockfile."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(version: str) -> int:
    paths = [ROOT / "pyproject.toml", *sorted((ROOT / "packages").glob("*/pyproject.toml")), ROOT / "uv.lock"]
    originals = {path: path.read_bytes() if path.exists() else None for path in paths}
    try:
        return subprocess.run(["bash", str(ROOT / "build.sh"), version], cwd=ROOT, check=False).returncode
    finally:
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                _ = path.write_bytes(original)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 scripts/build_release.py <version>")
    sys.exit(build(sys.argv[1]))
