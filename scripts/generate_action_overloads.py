#!/usr/bin/env python3
"""Generate the per-action `execute()` overloads from the action registry.

`NotteSession.execute/aexecute` (notte-browser) and `RemoteSession.execute` (notte-sdk) take an
action as keyword arguments, typed by one `**kwargs: Unpack[XxxActionDict]` overload per action.
This script writes those overloads between the markers

    # BEGIN GENERATED OVERLOADS: <method> (scripts/generate_action_overloads.py)
    # END GENERATED OVERLOADS: <method>

in `notte_core.actions.typedicts.ActionDict` order, leaving out the actions each session hides,
and keeps the `from notte_core.actions.typedicts import (...)` statement of each file in sync.
Run it after adding, removing or hiding an action:

    uv run --no-sync python scripts/generate_action_overloads.py           # rewrite the files
    uv run --no-sync python scripts/generate_action_overloads.py --check   # fail if out of date (pre-commit)
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args, get_type_hints

from notte_core.actions.actions import BrowserAction
from notte_core.actions.typedicts import ActionDict

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_SESSION = REPO_ROOT / "packages/notte-browser/src/notte_browser/session.py"
REMOTE_SESSION = REPO_ROOT / "packages/notte-sdk/src/notte_sdk/endpoints/sessions.py"
TYPEDICTS_MODULE = "notte_core.actions.typedicts"
LINE_LENGTH = 120  # [tool.ruff] line-length

# Local sessions run every listed browser action; they cannot run the API-side ones.
LOCAL_HIDDEN_ACTIONS: frozenset[str] = BrowserAction.unlisted_action_types()
# Cloud sessions also run the API-side actions (`BrowserAction.REMOTE_ONLY_ACTION_TYPES`).
REMOTE_HIDDEN_ACTIONS: frozenset[str] = (
    BrowserAction.LEGACY_AGENT_ACTION_TYPES
    | BrowserAction.PERSONA_INBOX_ACTION_TYPES
    | BrowserAction.RECORD_ONLY_ACTION_TYPES
)


@dataclass(frozen=True)
class Target:
    path: Path
    method: str
    is_async: bool
    hidden: frozenset[str]
    # where the `execute(action: BaseAction)` overload goes relative to the per-action ones
    action_overload: Literal["first", "last"]

    @property
    def begin(self) -> str:
        return f"# BEGIN GENERATED OVERLOADS: {self.method} (scripts/generate_action_overloads.py)"

    @property
    def end(self) -> str:
        return f"# END GENERATED OVERLOADS: {self.method}"


TARGETS: tuple[Target, ...] = (
    Target(LOCAL_SESSION, "aexecute", is_async=True, hidden=LOCAL_HIDDEN_ACTIONS, action_overload="first"),
    Target(LOCAL_SESSION, "execute", is_async=False, hidden=LOCAL_HIDDEN_ACTIONS, action_overload="first"),
    Target(REMOTE_SESSION, "execute", is_async=False, hidden=REMOTE_HIDDEN_ACTIONS, action_overload="last"),
)


def action_type_of(typed_dict: type) -> str:
    (action_type,) = get_args(get_type_hints(typed_dict)["type"])
    return action_type


def overload_typedicts(hidden: frozenset[str]) -> list[str]:
    """Names of the TypedDicts that get an overload, in `ActionDict` order."""
    return [td.__name__ for td in get_args(ActionDict) if action_type_of(td) not in hidden]


def _overload(target: Target, params: str) -> str:
    prefix = "async def" if target.is_async else "def"
    one_line = f"    {prefix} {target.method}({params}) -> ExecutionResult: ..."
    if len(one_line) <= LINE_LENGTH:
        return f"    @overload\n{one_line}\n"
    # the layout `ruff format` gives a signature that does not fit on one line
    return f"    @overload\n    {prefix} {target.method}(\n        {params}\n    ) -> ExecutionResult: ...\n"


def render_overloads(target: Target) -> str:
    """The overloads of `target`, markers included, indented as class members."""
    action = _overload(target, "self, action: BaseAction, *, raise_on_failure: bool | None = None")
    per_action = [
        _overload(target, f"self, *, raise_on_failure: bool | None = None, **kwargs: Unpack[{name}]")
        for name in overload_typedicts(target.hidden)
    ]
    overloads = [action, *per_action] if target.action_overload == "first" else [*per_action, action]
    # `ruff format` puts a blank line between the last overload and the comment that follows it
    return f"    {target.begin}\n{''.join(overloads)}\n    {target.end}\n"


def _replace_region(source: str, target: Target) -> str:
    pattern = re.compile(
        rf"^    {re.escape(target.begin)}\n.*?^    {re.escape(target.end)}\n", re.MULTILINE | re.DOTALL
    )
    matches = pattern.findall(source)
    if len(matches) != 1:
        raise SystemExit(
            f"{target.path.relative_to(REPO_ROOT)}: expected one '{target.begin}' ... '{target.end}' region"
        )
    return pattern.sub(lambda _: render_overloads(target), source)


def _member_sort_key(name: str) -> tuple[int, str]:
    # ruff's isort order for imported members: CONSTANTS, then Classes, then functions
    kind = 0 if name.isupper() else 1 if name[0].isupper() else 2
    return kind, name.lower()


def _sync_typedict_import(source: str, targets: list[Target]) -> str:
    """Import exactly the ActionDicts the file uses, keeping the other names of the statement."""
    tree = ast.parse(source)
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == TYPEDICTS_MODULE]
    if len(imports) != 1:
        raise SystemExit(f"expected one 'from {TYPEDICTS_MODULE} import (...)' statement")
    statement = imports[0]
    lines = source.splitlines(keepends=True)
    start, end = statement.lineno - 1, statement.end_lineno or statement.lineno
    rest = "".join(lines[:start] + lines[end:])
    used = set(re.findall(r"\b(\w+ActionDict)\b", rest))
    for target in targets:
        used.update(overload_typedicts(target.hidden))
    others = {alias.name for alias in statement.names if not alias.name.endswith("ActionDict")}
    names = sorted(used | others, key=_member_sort_key)
    rendered = f"from {TYPEDICTS_MODULE} import (\n" + "".join(f"    {name},\n" for name in names) + ")\n"
    return "".join(lines[:start]) + rendered + "".join(lines[end:])


def generate(path: Path, source: str) -> str:
    """`source` of `path` with its generated overloads and TypedDict import up to date."""
    targets = [target for target in TARGETS if target.path == path]
    for target in targets:
        source = _replace_region(source, target)
    return _sync_typedict_import(source, targets)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = parser.add_argument("--check", action="store_true", help="fail instead of rewriting out-of-date files")
    args = parser.parse_args()

    stale: list[Path] = []
    for path in dict.fromkeys(target.path for target in TARGETS):
        source = path.read_text()
        generated = generate(path, source)
        if generated == source:
            continue
        stale.append(path)
        if not args.check:
            _ = path.write_text(generated)

    for path in stale:
        verb = "is out of date" if args.check else "regenerated"
        print(f"{path.relative_to(REPO_ROOT)} {verb}", file=sys.stderr)
    if args.check and stale:
        print("Run: uv run --no-sync python scripts/generate_action_overloads.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
