"""Guard against overload order that breaks astral `ty` with open Unpack[TypedDict].

`ty` treats `**kwargs: Unpack[OpenTypedDict]` as accepting unknown keyword names.
If a broad Unpack overload appears before more specific ones (e.g. scrape's
`response_format=` / `instructions=`), `ty` picks the first match and callers
see the wrong return type (typically `str` instead of a Pydantic model).

basedpyright rejects those unknown kwargs, so the same order can look fine
under pyright. Keep most-specific overloads first and any open-Unpack catch-all
last.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOTS = (
    REPO_ROOT / "packages",
    REPO_ROOT / "src",
)
SKIP_PARTS = {".venv", "site-packages", "dist", "build", "typing_cases", "tests"}


@dataclass(frozen=True)
class OverloadInfo:
    return_annotation: str | None
    required_kwonly: tuple[str, ...]
    has_unpack: bool
    lineno: int


@dataclass(frozen=True)
class OverloadGroup:
    path: Path
    qualname: str
    overloads: tuple[OverloadInfo, ...]

    @property
    def label(self) -> str:
        return f"{self.path.relative_to(REPO_ROOT)}::{self.qualname}"


def _decorator_is_overload(decorator: ast.expr) -> bool:
    return (isinstance(decorator, ast.Name) and decorator.id == "overload") or (
        isinstance(decorator, ast.Attribute) and decorator.attr == "overload"
    )


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in PACKAGE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            files.append(path)
    return files


def _required_kwonly(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    required: list[str] = []
    for arg, default in zip(fn.args.kwonlyargs, fn.args.kw_defaults, strict=True):
        if default is None:
            required.append(arg.arg)
    return tuple(required)


def _collect_overload_groups(path: Path) -> list[OverloadGroup]:
    source = path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    groups: list[OverloadGroup] = []

    def visit_body(nodes: list[ast.stmt], class_name: str | None) -> None:
        index = 0
        while index < len(nodes):
            node = nodes[index]
            if isinstance(node, ast.ClassDef):
                visit_body(node.body, node.name)
                index += 1
                continue

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                same_name: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
                while (
                    index < len(nodes)
                    and isinstance(nodes[index], (ast.FunctionDef, ast.AsyncFunctionDef))
                    and nodes[index].name == name  # type: ignore[union-attr]
                ):
                    same_name.append(nodes[index])  # type: ignore[arg-type]
                    index += 1

                overloads = [fn for fn in same_name if any(_decorator_is_overload(d) for d in fn.decorator_list)]
                if len(overloads) < 2:
                    continue

                infos: list[OverloadInfo] = []
                for fn in overloads:
                    segment = ast.get_source_segment(source, fn) or ""
                    ret = ast.get_source_segment(source, fn.returns) if fn.returns is not None else None
                    infos.append(
                        OverloadInfo(
                            return_annotation=ret,
                            required_kwonly=_required_kwonly(fn),
                            has_unpack="Unpack[" in segment,
                            lineno=fn.lineno,
                        )
                    )

                qualname = f"{class_name}.{name}" if class_name else name
                groups.append(OverloadGroup(path=path, qualname=qualname, overloads=tuple(infos)))
                continue

            index += 1

    visit_body(tree.body, None)
    return groups


def _discriminating_required(info: OverloadInfo) -> tuple[str, ...]:
    return tuple(name for name in info.required_kwonly if name not in {"raise_on_failure"})


def _is_risky_for_ty(group: OverloadGroup) -> bool:
    """True when a broad open-Unpack overload can steal later, more specific overloads under ty."""
    returns = {info.return_annotation for info in group.overloads}
    if len(returns) <= 1:
        return False

    for index, info in enumerate(group.overloads):
        if not info.has_unpack:
            continue
        if _discriminating_required(info):
            continue
        later = group.overloads[index + 1 :]
        if any(_discriminating_required(other) or (not other.has_unpack and other.required_kwonly) for other in later):
            return True
    return False


def test_no_broad_unpack_overload_before_specific_return_overloads() -> None:
    risky = [
        group for path in _iter_python_files() for group in _collect_overload_groups(path) if _is_risky_for_ty(group)
    ]
    if not risky:
        return

    details = "\n".join(
        f"  - {group.label} (first broad Unpack at line {next(i.lineno for i in group.overloads if i.has_unpack and not _discriminating_required(i))})"
        for group in risky
    )
    raise AssertionError(
        "Found overload groups where an open Unpack[...] catch-all appears before more specific "
        "overloads with different return types. Under astral ty this makes structured calls "
        "resolve to the catch-all return type (often str).\n"
        "Reorder so discriminating overloads come first and the Unpack catch-all is last.\n"
        f"{details}"
    )


@pytest.mark.parametrize(
    "qualname_suffix",
    [
        "NotteClient.scrape",
        "RemoteSession.scrape",
        "PageClient.scrape",
        "NotteSession.scrape",
        "NotteSession.ascrape",
    ],
)
def test_scrape_overload_groups_keep_catch_all_last(qualname_suffix: str) -> None:
    matches = [
        group
        for path in _iter_python_files()
        for group in _collect_overload_groups(path)
        if group.qualname.endswith(qualname_suffix)
    ]
    assert matches, f"expected overload group for {qualname_suffix}"
    for group in matches:
        last = group.overloads[-1]
        assert last.has_unpack, f"{group.label}: last overload should be Unpack catch-all"
        assert last.return_annotation == "str", f"{group.label}: catch-all should return str"
        assert not _discriminating_required(last), f"{group.label}: catch-all must not require discriminating kwargs"
        assert not _is_risky_for_ty(group), f"{group.label} is still risky for ty"
