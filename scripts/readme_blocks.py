"""Check the fenced code blocks in README.md.

Subcommands:
  extract           write TypeScript blocks (plus a tsconfig) to node-sdk/.readme-check/
  check             syntax-check Python and shell blocks
  setup-commands    print the install/setup commands from shell blocks, one per line
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
TS_OUT = ROOT / "node-sdk" / ".readme-check"

FENCE = re.compile(r"^```([\w-]*)[^\n]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
SHELL_LANGS = {"bash", "sh", "shell", "console"}
TS_LANGS = {"typescript", "ts"}
PY_LANGS = {"python", "py"}
# Commands a reader is expected to copy and run as-is. Anything else (curl calls that need
# a real API key, long-running jobs) is only syntax-checked.
SETUP_COMMAND = re.compile(
    r"^(pip install|uv add|uv pip install|npm install|patchright install|playwright install|npx (-y )?skills add|claude mcp add)\b"
)


def blocks(langs: set[str]) -> list[tuple[int, str]]:
    text = README.read_text()
    found: list[tuple[int, str]] = []
    for match in FENCE.finditer(text):
        if match.group(1).lower() in langs:
            line = text.count("\n", 0, match.start()) + 1
            found.append((line, match.group(2)))
    return found


def extract() -> None:
    TS_OUT.mkdir(parents=True, exist_ok=True)
    for old in TS_OUT.glob("*.mts"):
        old.unlink()
    files: list[str] = []
    for line, code in blocks(TS_LANGS):
        name = f"readme_L{line}.mts"
        _ = (TS_OUT / name).write_text(code)
        files.append(name)
    tsconfig = {
        "compilerOptions": {
            "target": "ES2022",
            "module": "ESNext",
            "moduleResolution": "Bundler",
            "strict": True,
            "noEmit": True,
            "skipLibCheck": True,
            "types": ["node"],
            "typeRoots": ["../node_modules/@types"],
            "paths": {"notte-sdk": ["../dist/index.d.ts"]},
        },
        "files": files,
    }
    _ = (TS_OUT / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2) + "\n")
    print(f"Extracted {len(files)} TypeScript block(s) to {TS_OUT.relative_to(ROOT)}")


def check() -> None:
    failures = 0
    python_blocks = blocks(PY_LANGS)
    for line, code in python_blocks:
        try:
            _ = compile(code, f"README.md:{line}", "exec")
        except SyntaxError as e:
            failures += 1
            print(f"README.md:{line}: Python syntax error: {e}", file=sys.stderr)
    shell_blocks = blocks(SHELL_LANGS)
    for line, code in shell_blocks:
        with tempfile.NamedTemporaryFile("w", suffix=".sh") as f:
            _ = f.write(code)
            f.flush()
            result = subprocess.run(["bash", "-n", f.name], check=False, capture_output=True, text=True)
        if result.returncode != 0:
            failures += 1
            print(f"README.md:{line}: shell syntax error: {result.stderr.strip()}", file=sys.stderr)
    if failures:
        sys.exit(1)
    print(f"Syntax-checked {len(python_blocks)} Python and {len(shell_blocks)} shell block(s)")


def setup_commands() -> None:
    # Unlabeled fences are included: install snippets are often written without a language.
    for _, code in blocks(SHELL_LANGS | {""}):
        for raw in code.splitlines():
            command = raw.split(" #", 1)[0].strip()
            if SETUP_COMMAND.match(command):
                print(command)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = parser.add_argument("command", choices=["extract", "check", "setup-commands"])
    args = parser.parse_args()
    {"extract": extract, "check": check, "setup-commands": setup_commands}[args.command]()


if __name__ == "__main__":
    main()
