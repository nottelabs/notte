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


def blocks(readme: Path, langs: set[str]) -> list[tuple[int, str]]:
    text = readme.read_text()
    found: list[tuple[int, str]] = []
    for match in FENCE.finditer(text):
        if match.group(1).lower() in langs:
            line = text.count("\n", 0, match.start()) + 1
            found.append((line, match.group(2)))
    return found


def extract(readme: Path, out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.mts"):
        old.unlink()
    files: list[str] = []
    for line, code in blocks(readme, TS_LANGS):
        name = f"readme_L{line}.mts"
        _ = (out / name).write_text(code)
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
    _ = (out / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2) + "\n")
    return files


def syntax_errors(readme: Path) -> list[str]:
    errors: list[str] = []
    for line, code in blocks(readme, PY_LANGS):
        try:
            _ = compile(code, f"{readme.name}:{line}", "exec")
        except SyntaxError as e:
            errors.append(f"{readme.name}:{line}: Python syntax error: {e}")
    for line, code in blocks(readme, SHELL_LANGS):
        with tempfile.NamedTemporaryFile("w", suffix=".sh") as f:
            _ = f.write(code)
            f.flush()
            result = subprocess.run(["bash", "-n", f.name], check=False, capture_output=True, text=True)
        if result.returncode != 0:
            errors.append(f"{readme.name}:{line}: shell syntax error: {result.stderr.strip()}")
    return errors


def shell_commands(code: str) -> list[str]:
    """Split a shell block into commands, joining backslash-continued lines and dropping comments."""
    commands: list[str] = []
    current = ""
    for raw in code.splitlines():
        line = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if line.endswith("\\"):
            current += line[:-1].strip() + " "
            continue
        command = (current + line.strip()).strip()
        current = ""
        if command:
            commands.append(command)
    if current.strip():
        commands.append(current.strip())
    return commands


def setup_commands(readme: Path) -> list[str]:
    # Unlabeled fences are included: install snippets are often written without a language.
    return [
        command
        for _, code in blocks(readme, SHELL_LANGS | {""})
        for command in shell_commands(code)
        if SETUP_COMMAND.match(command)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = parser.add_argument("command", choices=["extract", "check", "setup-commands"])
    _ = parser.add_argument("--readme", type=Path, default=README)
    args = parser.parse_args()
    readme: Path = args.readme
    if args.command == "extract":
        files = extract(readme, TS_OUT)
        print(f"Extracted {len(files)} TypeScript block(s) to {TS_OUT.relative_to(ROOT)}")
    elif args.command == "check":
        errors = syntax_errors(readme)
        for error in errors:
            print(error, file=sys.stderr)
        if errors:
            sys.exit(1)
        print(f"Syntax-checked Python and shell blocks in {readme.name}")
    else:
        for command in setup_commands(readme):
            print(command)


if __name__ == "__main__":
    main()
