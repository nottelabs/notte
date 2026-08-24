"""Parsing and sandboxed execution of user-authored Notte functions.

`ScriptValidator` decides what a submitted script is allowed to contain and
pulls the signature of its `run` entry point back out. `SecureScriptRunner`
executes it, either under RestrictedPython or, by default, in plain Python with
a builtins allowlist that withholds `eval`, `exec`, `compile`, `open` and
`__import__`, substituting sandboxed versions of the last two.

Variables arriving from a caller are coerced to match the entry point's
annotations before it is invoked, so a JSON or Python-literal string sent for a
`list` or `dict` parameter becomes the collection it spells out rather than
being iterated character by character.
"""

import ast
import builtins
import copy
import json
import re
import sys
import traceback
import types
from collections.abc import Iterable
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, cast, final

from pydantic import BaseModel, ConfigDict
from RestrictedPython import (
    compile_restricted,  # type: ignore [reportMissingTypeStubs]
    safe_globals,  # type: ignore [reportMissingTypeStubs]
)
from RestrictedPython.transformer import (
    RestrictingNodeTransformer,
)
from typing_extensions import override

from notte_core.common.logging import logger


def module_scope_statements(body: list[ast.stmt]) -> list[ast.stmt]:
    """Statements that execute in module scope, flattened in source order.

    Descends through control flow - ``if`` / ``try`` / ``with`` / loops - because
    a definition there still binds at module scope. Never descends into a class
    body or a nested function, whose ``run`` is not reachable as
    ``globals()["run"]``.

    Lives here rather than beside the schema check so that the upload validator
    and ``check_run_returns_pydantic_model`` cannot drift on what the entry point
    is. When they did, a ``run`` defined inside ``if`` was accepted by the
    validator and then rejected for having no verifiable return model.
    """
    out: list[ast.stmt] = []
    for node in body:
        out.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for field_name in ("body", "orelse", "finalbody"):
            nested: list[ast.stmt] = getattr(node, field_name, None) or []
            out.extend(module_scope_statements(nested))
        handlers: list[ast.ExceptHandler] = getattr(node, "handlers", None) or []
        for handler in handlers:
            out.extend(module_scope_statements(handler.body))
        # `match` is control flow like any other: a case body binds at module
        # scope, and skipping it hid rebindings entirely.
        cases: list[ast.match_case] = getattr(node, "cases", None) or []
        for case in cases:
            out.extend(module_scope_statements(case.body))
    return out


def _pattern_binds_run(pattern: ast.pattern | None) -> bool:
    """Whether a match pattern captures into the name ``run``.

    ``case str() as run:`` and ``case [*run]:`` bind the name just as an
    assignment would, and nest arbitrarily inside or/sequence patterns.
    """
    if pattern is None:
        return False
    for node in ast.walk(pattern):
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == "run":
            return True
        if isinstance(node, ast.MatchMapping) and node.rest == "run":
            return True
    return False


def _target_rebinds_run(target: ast.expr) -> bool:
    """Whether an assignment target binds ``run``, including through unpacking.

    ``run, other = f, 1`` and ``[run] = [f]`` bind it just as ``run = f`` does,
    and starred targets nest one level deeper again.
    """
    match target:
        case ast.Name(id="run"):
            return True
        case ast.Tuple(elts=elts) | ast.List(elts=elts):
            return any(_target_rebinds_run(e) for e in elts)
        case ast.Starred(value=value):
            return _target_rebinds_run(value)
        case _:
            return False


def _statement_rebinds_run(node: ast.stmt) -> bool:
    """Whether a module-scope statement rebinds or removes ``run``.

    Assignment is only the most obvious way to replace the name. Every binding
    form Python offers has to be covered, because each leaves the validated
    definition describing something the runtime will not call - or, for ``del``,
    nothing at all:

    ``run = f`` / ``run, x = f, 1`` / ``run: C = f`` / ``run += 1``
    ``for run in ...`` / ``async for run in ...``
    ``import json as run`` / ``from x import y as run``
    ``with open(p) as run`` / ``except ValueError as run``
    ``class run: ...``
    ``del run``
    """
    match node:
        case ast.Assign(targets=targets):
            return any(_target_rebinds_run(t) for t in targets)
        case ast.AnnAssign(target=target) | ast.AugAssign(target=target):
            return _target_rebinds_run(target)
        case ast.For(target=target) | ast.AsyncFor(target=target):
            return _target_rebinds_run(target)
        case ast.Delete(targets=targets):
            return any(_target_rebinds_run(t) for t in targets)
        case ast.Import(names=names) | ast.ImportFrom(names=names):
            # `import json as run`, and plain `import run` which binds the
            # top-level package name.
            return any((alias.asname or alias.name.split(".")[0]) == "run" for alias in names)
        case ast.With(items=items) | ast.AsyncWith(items=items):
            return any(item.optional_vars is not None and _target_rebinds_run(item.optional_vars) for item in items)
        case ast.Try(handlers=handlers):
            # `except ValueError as run` binds, then unbinds at the end of the
            # handler - either way the name no longer holds the definition.
            return any(handler.name == "run" for handler in handlers)
        case ast.ClassDef(name="run"):
            return True
        case ast.Match(cases=cases):
            return any(_pattern_binds_run(case.pattern) for case in cases)
        case _:
            return False


def _rebinding_after(definition: ast.stmt, tree: ast.Module) -> ast.stmt | None:
    """The first statement that rebinds ``run`` after ``definition``, if any.

    Order matters. ``run = print`` *before* the definition is harmless - the def
    executes later and wins - so rejecting it would fail a script Python handles
    unambiguously. Only a rebinding that runs afterwards leaves the name holding
    something other than the validated function.
    """
    statements = module_scope_statements(tree.body)
    try:
        start = statements.index(definition)
    except ValueError:  # pragma: no cover - definition always comes from this list
        return None
    return next((node for node in statements[start + 1 :] if _statement_rebinds_run(node)), None)


def resolve_run_entry_point(tree: ast.Module) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """The single top-level ``def run`` the runtime will call, or None.

    None whenever the binding is not knowable from the source: several
    definitions, one hidden under control flow that may never execute, or a
    later assignment over the name. ``ScriptValidator`` raises on each of those
    with a specific message; callers that only need to know whether a contract
    can be trusted use this and get None.
    """
    top_level = [
        node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run"
    ]
    if len(top_level) != 1:
        return None

    nested = [
        node
        for node in module_scope_statements(tree.body)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run"
    ]
    if len(nested) != 1:
        return None

    if _rebinding_after(top_level[0], tree) is not None:
        return None

    # A decorator binds its own return value to the name, not the function
    # written below it. That value can take different arguments and return a
    # different type, so the annotation here describes something the runtime
    # may never call.
    if top_level[0].decorator_list:
        return None

    return top_level[0]


class MissingRunFunctionError(Exception):
    """Raised when a script does not contain a required 'run' function"""


class AmbiguousRunFunctionError(Exception):
    """Raised when a script binds ``run`` more than once at module scope.

    Which definition executes is then either a source-order accident (two
    sequential ``def run``, where the second silently discards the first) or not
    knowable at all (``if`` / ``else`` branches picked at runtime). Everything
    downstream - the advertised parameters, the verified return model, the
    schema shown in the marketplace - would describe whichever one this code
    happened to choose, which may not be the one that runs.

    Rejecting is the honest option: one entry point per function, stated
    clearly at upload, rather than a contract that is right by luck.
    """


class ParameterInfo(BaseModel):
    """Information about a function parameter"""

    name: str
    type: str | None = None
    default: str | None = None


_SEQUENCE_HEADS = frozenset({"list", "tuple", "set", "frozenset", "sequence", "iterable"})
_MAPPING_HEADS = frozenset({"dict", "mapping", "ordereddict", "defaultdict"})
_TRANSPARENT_HEADS = frozenset({"optional", "annotated", "union", "final"})


def _annotation_head(node: ast.expr) -> str | None:
    """Lowercased name of a subscript head, ignoring the module it came from."""
    if isinstance(node, ast.Name):
        return node.id.lower()
    if isinstance(node, ast.Attribute):
        return node.attr.lower()
    if isinstance(node, ast.Subscript):
        return _annotation_head(node.value)
    return None


def _container_kind(annotation: str | None) -> str | None:
    """
    Which container an annotation asks for, or None for anything else.

    Read from the *outermost* type, so `dict[str, list[str]]` is a mapping
    rather than a sequence that happens to mention one. Wrappers that do not
    change the shape are looked through: `Optional[list[str]]`,
    `Annotated[list[str], Field(...)]`, `list[str] | None`, and the `Union[...]`
    spelling of the same. A union that names more than one container resolves to
    a mapping, since guessing a sequence for something that might be a dict is
    the more expensive mistake.

    Quoted annotations are unwrapped and re-read, since `ast.unparse` keeps the
    quotes a forward reference was written with.

    Parsed rather than pattern-matched: `ast.unparse` produced these strings, so
    `ast.parse` reads them back exactly, including nesting the eye slides over.
    """
    if not annotation:
        return None
    try:
        node: ast.expr = ast.parse(annotation.strip(), mode="eval").body
    except SyntaxError:
        return None

    kinds: set[str] = set()

    def walk(current: ast.expr, depth: int = 0) -> None:
        if depth > 8:  # A pathological annotation is not worth recursing into.
            return
        if isinstance(current, ast.Constant) and isinstance(current.value, str):
            # A quoted annotation. `def f(x: "list[str]")` is recorded by
            # `ast.unparse` as the six characters `'list[str]'`, quotes and all,
            # so without this the string reads as a bare constant of no
            # particular type and the parameter silently keeps its raw value.
            # Reached again for the inner half of `Optional["list[str]"]`.
            try:
                walk(ast.parse(current.value.strip(), mode="eval").body, depth + 1)
            except SyntaxError:
                pass
            return
        if isinstance(current, ast.BinOp) and isinstance(current.op, ast.BitOr):
            walk(current.left, depth + 1)
            walk(current.right, depth + 1)
            return
        if isinstance(current, ast.Subscript):
            head = _annotation_head(current.value)
            if head in _TRANSPARENT_HEADS:
                inner = current.slice
                # `Annotated[T, ...]` and `Union[A, B]` both arrive as a tuple.
                if isinstance(inner, ast.Tuple):
                    members = inner.elts if head != "annotated" else inner.elts[:1]
                    for member in members:
                        walk(member, depth + 1)
                else:
                    walk(inner, depth + 1)
                return
            if head in _SEQUENCE_HEADS:
                kinds.add("sequence")
            elif head in _MAPPING_HEADS:
                kinds.add("mapping")
            return
        head = _annotation_head(current)
        if head in _SEQUENCE_HEADS:
            kinds.add("sequence")
        elif head in _MAPPING_HEADS:
            kinds.add("mapping")

    walk(node)
    if "mapping" in kinds:
        return "mapping"
    if "sequence" in kinds:
        return "sequence"
    return None


def _parse_collection_text(text: str, kind: str) -> Any | None:
    """
    A string that spells out a collection, as the collection, or None.

    Two spellings, because both reach this function in practice: JSON, which is
    what an HTTP caller sends, and the Python literal that `ast.unparse` writes
    for a parameter default, so a caller echoing a default back sends
    `['a', 'b']` with quotes JSON rejects.

    `ast.literal_eval` is the safe evaluator: literals and nothing else, so a
    name like `DEFAULT_KEYWORDS` or a call like `list()` raises here rather than
    being resolved or executed. `set()` is the one exception, and CPython's
    rather than ours: it is special-cased because there is no empty-set literal,
    so it evaluates to an empty set and a parameter defaulted that way arrives
    as `[]`. That is the value it asked for, and better than the four characters
    of source it used to receive.

    A set arrives as a list because JSON has no set. The wire format decided
    that long before this function saw the value.
    """
    try:
        value: Any = json.loads(text)
    except (ValueError, MemoryError, RecursionError):
        # More than ValueError because a parser can fail on the shape of the
        # input rather than its syntax: `json.loads` recurses per nesting level,
        # so deeply nested text raises RecursionError instead of rejecting it,
        # and a large enough document exhausts memory. Letting either escape
        # would end the run over a variable this function is allowed to decline.
        # Declining means passing the original string through, which is what
        # happens when both parsers fail. Same set the literal_eval arm catches,
        # for the same reason.
        #
        # Nested rather than a loop with `continue`, so neither attempt needs a
        # bare `except` and the exceptions each parser really raises stay named.
        try:
            value = ast.literal_eval(text)
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
            return None

    # `literal_eval` returns `Any`, so the narrowed types stay partially unknown
    # without saying what the elements are. They are whatever the caller wrote.
    if kind == "sequence" and isinstance(value, (list, tuple, set, frozenset)):
        return list(cast("Iterable[Any]", value))
    if kind == "mapping" and isinstance(value, dict):
        return cast("dict[Any, Any]", value)
    return None


def coerce_collection_variables(run_parameters: list["ParameterInfo"], variables: dict[str, Any]) -> dict[str, Any]:
    """
    Replace strings that spell out a collection with the collection itself.

    A caller that sends `keywords="['a', 'b']"` for `keywords: list[str]` is
    handing the script a 22-character string where it expects two items, and the
    script raises somewhere inside itself. Every client hits this: the callers
    that build the payload from a stored default are echoing back Python source,
    because that is what `ast.unparse` wrote when the parameter was recorded.

    Deliberately narrow, on the numbers. Across a fortnight of production runs,
    `int` and `bool` parameters received strings and succeeded 5,166 times,
    because Python is duck-typed and the scripts cope, so touching those would
    break working calls. A collection parameter that received a string failed
    every time it happened, 4 of 4 over thirty days, so there is no behaviour
    there to preserve and nothing this can regress.

    Nothing is rejected and nothing else is converted. A value this cannot read
    is passed through exactly as it arrived, which is what happened before.
    """
    if not variables:
        return variables

    kinds = {param.name: _container_kind(param.type) for param in run_parameters}
    for name, value in variables.items():
        kind = kinds.get(name)
        if kind is None or not isinstance(value, str):
            continue
        parsed = _parse_collection_text(value, kind)
        if parsed is not None:
            variables[name] = parsed
    return variables


class ParsedScriptInfo(BaseModel):
    """Information extracted from parsing a script"""

    model_config: ClassVar[ConfigDict] = ConfigDict(arbitrary_types_allowed=True)

    code: types.CodeType
    variables: list[ParameterInfo]


class NotteModule(Protocol):
    Chapter: type
    Agent: type
    Session: type


_GETATTR_MISSING_DEFAULT = object()


class ScriptValidator(RestrictingNodeTransformer):
    """Validates that the AST only contains allowed operations"""

    # Modules that can be imported in user scripts.
    # Most standard-library modules are allowed, but modules that provide direct
    # process control, filesystem access, raw sockets, dynamic imports, or native
    # memory access stay blocked.
    DISALLOWED_STDLIB_IMPORTS: ClassVar[set[str]] = {
        "_ctypes",
        "_elementtree",
        "_imp",
        "_io",
        "_multiprocessing",
        "_pickle",
        "_posixshmem",
        "_posixsubprocess",
        "_signal",
        "_socket",
        "_sqlite3",
        "_thread",
        "asyncio.subprocess",
        "builtins",
        "code",
        "codeop",
        "compileall",
        "configparser",
        "ctypes",
        "dbm",
        "filecmp",
        "fileinput",
        "fcntl",
        "gc",
        "glob",
        "grp",
        "importlib",
        "inspect",
        "linecache",
        "mmap",
        "modulefinder",
        "marshal",
        "multiprocessing",
        "nt",
        "os",
        "pathlib",
        "pickle",
        "pickletools",
        "pkgutil",
        "posix",
        "pty",
        "pwd",
        "py_compile",
        "resource",
        "runpy",
        "shelve",
        "shutil",
        "signal",
        "socket",
        "socketserver",
        "sqlite3",
        "subprocess",
        "sys",
        "sysconfig",
        "tarfile",
        "tempfile",
        "termios",
        "threading",
        "tty",
        "venv",
        "winreg",
        "xml",
        "zipapp",
        "zipfile",
        "zipimport",
    }
    DISALLOWED_IMPORT_MEMBERS: ClassVar[dict[str, set[str]]] = {
        "_io": {"FileIO", "open", "open_code"},
        "asyncio": {"create_subprocess_exec", "create_subprocess_shell", "subprocess", "to_thread"},
        "codecs": {"open"},
        "io": {"FileIO", "open", "open_code"},
    }
    ALLOWED_IMPORTS: ClassVar[set[str]] = (set(sys.stdlib_module_names) - DISALLOWED_STDLIB_IMPORTS) | {
        # Notte ecosystem
        "notte",
        "notte_browser",
        "notte_sdk",
        "notte_agent",
        "notte_core",
        "notte_llm",
        "tqdm",
        # Third-party
        "pydantic",  # Data validation library
        "loguru",  # Logging library
        "requests",
        # Sync and async HTTP in one library. `requests` alone left async
        # functions with no client at all, so `asyncio` was only ever usable to
        # drive a thread pool - the one thing it is worst at. Present in the
        # runner image already: litellm's module-level clients are httpx.Client
        # and httpx.AsyncClient, verified against the deployed image rather than
        # inferred from the dependency tree.
        "httpx",
        # requests-compatible client that emulates a browser's TLS/HTTP2
        # fingerprint. `requests` and `httpx` are both trivially fingerprintable,
        # so a function scraping a site behind bot detection had no in-sandbox
        # option that was not a browser session. Ships a bundled shared library
        # it loads with ctypes from its own package directory - no subprocess and
        # nothing written at runtime, so it holds under Lambda's read-only image.
        "httpcloak",
        "playwright",
        "gspread",
        "google",
        "litellm",
        "bs4",
        "pipedream",
        "typing_extensions",  # Extended type hints
    }

    FORBIDDEN_NODES: set[type[ast.AST]] = {
        # Dangerous operations - removed ast.Import and ast.ImportFrom to handle separately
        # ast.FunctionDef,  # Allow function definitions but validate them separately
        # ast.AsyncFunctionDef,
        # ast.ClassDef,
        ast.Global,
        ast.Nonlocal,
        # # Allow try/except blocks to be used in scripts
        # # ast.Try,
        # # ast.ExceptHandler,
        ast.TryStar,
        # # Advanced features that could be misused
        ast.Lambda,
        # ast.GeneratorExp,
        # ast.Yield,
        # ast.YieldFrom,
        # ast.Await,
        ast.Delete,
        # ast.AugAssign,
        # ast.AsyncFunctionDef,
    }

    FORBIDDEN_CALLS: set[str] = {
        "input",
        # "print",  # print might be OK depending on your needs
        # "hash",
        "__import__",
        "exec",
        "eval",
        "compile",
        "globals",
        "locals",
        "vars",
        "dir",
        "setattr",
        "delattr",
        "id",
        "memoryview",
        "_io.FileIO",
        "_io.open",
        "_io.open_code",
        "asyncio.create_subprocess_exec",
        "asyncio.create_subprocess_shell",
        "asyncio.to_thread",
        "codecs.open",
        "io.FileIO",
        "io.open",
        "io.open_code",
    }

    RESTRICTED_INTERNAL_NAMES: ClassVar[set[str]] = {
        "_apply_",
        "_getattr_",
        "_getitem_",
        "_getiter_",
        "_inplacevar_",
        "_iter_unpack_sequence_",
        "_print",
        "_print_",
        "_unpack_sequence_",
        "_write_",
    }

    @override
    def check_name(
        self,
        node: ast.AST,
        name: str | None,
        allow_magic_methods: bool = False,
    ) -> None:
        if name is not None and name.startswith("_") and not name.startswith("__"):
            if name in self.RESTRICTED_INTERNAL_NAMES or re.fullmatch(r"_tmp[0-9]+", name):
                super().check_name(node, name, allow_magic_methods)  # pyright: ignore[reportUnknownMemberType]
            return

        if name == "__name__" and isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            return

        super().check_name(node, name, allow_magic_methods)  # pyright: ignore[reportUnknownMemberType]

    @override
    def visit_Constant(self, node: ast.Constant) -> ast.AST | None:
        """Allow Python's Ellipsis literal (`...`) in user scripts."""
        if node.value is Ellipsis:
            return node

        return super().visit_Constant(node)

    @override
    def visit_Call(self, node: ast.Call) -> ast.AST:
        """Override to add custom call restrictions"""
        call_name = self._get_call_name(node)

        if call_name and call_name in self.FORBIDDEN_CALLS:
            raise SyntaxError(f"Forbidden function call: '{call_name}'")

        return super().visit_Call(node)

    def _get_call_name(self, node: ast.Call) -> str | None:
        """Extract the full call name from a Call node"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                return f"{node.func.value.id}.{node.func.attr}"
            elif isinstance(node.func.value, ast.Attribute):
                # Handle nested attributes like session.execute
                base = self._get_attr_name(node.func.value)
                return f"{base}.{node.func.attr}" if base else None
        return None

    def _get_attr_name(self, node: ast.Attribute | ast.Name | ast.expr) -> str | None:
        """Get attribute name recursively"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_attr_name(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    # Safe dunder methods that are allowed in user scripts
    ALLOWED_DUNDER_METHODS: ClassVar[set[str]] = {
        "__init__",
        "__str__",
        "__repr__",
        "__eq__",
        "__ne__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
        "__hash__",
        "__bool__",
        "__len__",
        "__getitem__",
        "__setitem__",
        "__delitem__",
        "__iter__",
        "__next__",
        "__contains__",
        "__add__",
        "__sub__",
        "__mul__",
        "__truediv__",
        "__floordiv__",
        "__mod__",
        "__pow__",
        "__and__",
        "__or__",
        "__xor__",
        "__enter__",
        "__exit__",
        "__aenter__",
        "__aexit__",
        "__call__",
        "__post_init__",  # For dataclasses
    }

    # Dangerous dunder attributes that should be blocked
    DANGEROUS_DUNDER_ATTRS: ClassVar[set[str]] = {
        "__class__",
        "__bases__",
        "__subclasses__",
        "__mro__",
        "__globals__",
        "__code__",
        "__func__",
        "__self__",
        "__dict__",
        "__getattribute__",
        "__setattr__",
        "__delattr__",
        "__import__",
        "__builtins__",
        "__loader__",
        "__spec__",
        "__cached__",
        "__file__",
        "__path__",
        "__package__",
    }

    @override
    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        """Override to add custom attribute access restrictions"""
        if hasattr(node, "attr"):
            attr_name = node.attr

            # Block dangerous dunder attributes
            if attr_name in self.DANGEROUS_DUNDER_ATTRS:
                raise SyntaxError(f"Access to dangerous attribute forbidden: '{attr_name}'")

            # Allow safe dunder methods (like __init__, __str__, etc.)
            if attr_name in self.ALLOWED_DUNDER_METHODS:
                return super().visit_Attribute(node)

            # Block all other private attributes (starting with _)
            if attr_name.startswith("_"):
                raise SyntaxError(f"Access to private attribute forbidden: '{attr_name}'")

        return super().visit_Attribute(node)

    @staticmethod
    def check_valid_import(name: str, import_type: Literal["import", "import from"] = "import") -> None:
        blocked = name in ScriptValidator.DISALLOWED_STDLIB_IMPORTS or any(
            name.startswith(f"{m}.") for m in ScriptValidator.DISALLOWED_STDLIB_IMPORTS
        )
        if blocked:
            raise SyntaxError(f"Import {'of' if import_type == 'import' else 'from'} '{name}' is not allowed")

        # Allow exact matches and explicitly whitelisted submodules
        allowed = name in ScriptValidator.ALLOWED_IMPORTS or any(
            name.startswith(f"{m}.") for m in ScriptValidator.ALLOWED_IMPORTS
        )
        if not allowed:
            raise SyntaxError(
                f"Import {'of' if import_type == 'import' else 'from'} '{name}' is not allowed. Allowed imports: {sorted(ScriptValidator.ALLOWED_IMPORTS)}"
            )

    @override
    def visit_Import(self, node: ast.Import) -> ast.AST:
        """Override to validate allowed imports"""
        for alias in node.names:
            ScriptValidator.check_valid_import(alias.name, import_type="import")
        return super().visit_Import(node)

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        """Override to validate allowed from imports"""
        if node.module is None:
            raise SyntaxError("Relative imports are not allowed")

        if node.module == "__future__":
            imported_names = {alias.name for alias in node.names}
            if imported_names == {"annotations"}:
                return super().visit_ImportFrom(node)
            raise SyntaxError("Only 'from __future__ import annotations' is allowed")

        blocked_members = ScriptValidator.DISALLOWED_IMPORT_MEMBERS.get(node.module, set())
        for alias in node.names:
            if alias.name == "*" or alias.name in blocked_members:
                raise SyntaxError(f"Import from '{node.module}' of '{alias.name}' is not allowed")

        ScriptValidator.check_valid_import(node.module, import_type="import from")
        return super().visit_ImportFrom(node)

    @override
    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        """Override to allow type annotations (useful for response schemas).

        RestrictedPython's default policy forbids AnnAssign.
        - We still visit children to validate annotation expressions.
        """
        _ = self.visit(node.annotation)
        _ = self.visit(node.target)
        if node.value is not None:
            _ = self.visit(node.value)
        return node

    @override
    def visit(self, node: ast.AST) -> ast.AST:
        """Override to add custom node restrictions"""
        if type(node) in self.FORBIDDEN_NODES:
            raise SyntaxError(f"Forbidden AST node in Notte script: {type(node).__name__}")
        return super().visit(node)

    @staticmethod
    def _module_scope_run_defs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
        """Definitions of ``run`` that end up bound in the module namespace.

        AsyncFunctionDef is a sibling of FunctionDef rather than a subclass, so
        matching only the latter reported a valid ``async def run()`` as missing
        and rejected the upload outright.

        The traversal descends through control flow (``if``, ``try``, ``with``,
        loops) because a definition there still binds at module scope, but never
        into a class body or another function: a method or closure named ``run``
        is not reachable as ``globals()["run"]``, so accepting one would pass an
        upload whose every invocation then fails to find an entry point.
        """
        return [
            node
            for node in module_scope_statements(tree.body)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run"
        ]

    @staticmethod
    def _check_run_entry_point(tree: ast.Module) -> ast.FunctionDef | ast.AsyncFunctionDef:
        """The single top-level ``def run``, or raise explaining why there isn't one.

        The runtime calls whatever ``globals()["run"]`` holds after the module
        finishes executing. Three shapes make that unknowable at upload time, and
        each one produces a function that looks fine here and fails later:

        * **More than one definition** - only the last executes, so the declared
          parameters and return model may describe the discarded one.
        * **Defined under control flow** - ``if cond: def run()`` binds nothing
          when ``cond`` is false, so the upload succeeds and every invocation
          then fails with no entry point.
        * **Rebound afterwards** - ``run = print`` leaves the advertised
          signature describing a function the runtime never calls.

        Requiring exactly one unconditional top-level definition, never
        reassigned, is what makes the stored contract true by construction
        rather than by luck.
        """
        top_level = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run"
        ]
        all_defs = ScriptValidator._module_scope_run_defs(tree)

        if len(all_defs) > 1:
            lines = ", ".join(str(node.lineno) for node in all_defs)
            detail = "Only the last one executes, so the declared parameters and return model may describe the wrong function."
            raise AmbiguousRunFunctionError(
                f"Python script must define 'run' exactly once, found {len(all_defs)} definitions (lines {lines}). {detail}"
            )

        if not top_level:
            if all_defs:
                detail = "Define 'run' at the top level of the module."
                raise AmbiguousRunFunctionError(
                    f"'run' is defined inside control flow (line {all_defs[0].lineno}), so it may never be bound. {detail}"
                )
            raise MissingRunFunctionError("Python script must contain a 'run' function")

        rebind = _rebinding_after(top_level[0], tree)
        if rebind is not None:
            detail = "The runtime calls the reassigned value, which the declared parameters no longer describe."
            raise AmbiguousRunFunctionError(f"'run' is reassigned at line {rebind.lineno}. {detail}")

        if top_level[0].decorator_list:
            detail = "A decorator binds its own return value to 'run', which may take different arguments and return a different type."
            raise AmbiguousRunFunctionError(f"'run' is decorated at line {top_level[0].lineno}. {detail}")

        return top_level[0]

    @staticmethod
    def _check_run_function_exists(tree: ast.Module) -> bool:
        """Check if the module binds a function named 'run' at module scope."""
        return len(ScriptValidator._module_scope_run_defs(tree)) > 0

    @staticmethod
    def _extract_run_function_parameters(tree: ast.Module) -> list[ParameterInfo]:
        """Extract parameter information from the 'run' function.

        Reversed because the last binding is the one the runtime calls. Reading
        the first definition would advertise the signature of a callable that
        was overwritten, so supplied variables would be rejected as unexpected
        while the ones the real function needs would be reported missing.
        """
        for node in reversed(ScriptValidator._module_scope_run_defs(tree)):
            parameters: list[ParameterInfo] = []

            # Handle regular arguments
            defaults_offset = len(node.args.args) - len(node.args.defaults)
            for i, arg in enumerate(node.args.args):
                param_name = arg.arg
                type_annotation = None
                default_value = None

                # Extract type annotation if present
                if arg.annotation:
                    try:
                        # Use ast.unparse for Python 3.9+ or fallback to basic string representation
                        type_annotation = ast.unparse(arg.annotation)
                    except AttributeError:
                        # Fallback for older Python versions (though we're on 3.11)
                        type_annotation = str(arg.annotation)

                # Extract default value if present
                if i >= defaults_offset:
                    default_index = i - defaults_offset
                    if default_index < len(node.args.defaults):
                        try:
                            default_value = ast.unparse(node.args.defaults[default_index])
                        except AttributeError:
                            default_value = str(node.args.defaults[default_index])

                parameters.append(ParameterInfo(name=param_name, type=type_annotation, default=default_value))

            # Handle keyword-only arguments
            if node.args.kwonlyargs:
                kw_defaults = node.args.kw_defaults or []
                for i, arg in enumerate(node.args.kwonlyargs):
                    param_name = arg.arg
                    type_annotation = None
                    default_value = None

                    # Extract type annotation if present
                    if arg.annotation:
                        try:
                            type_annotation = ast.unparse(arg.annotation)
                        except AttributeError:
                            type_annotation = str(arg.annotation)

                    # Extract default value if present
                    if i < len(kw_defaults) and kw_defaults[i] is not None:
                        default_node = kw_defaults[i]
                        if default_node is not None:
                            try:
                                default_value = ast.unparse(default_node)
                            except AttributeError:
                                default_value = str(default_node)

                    parameters.append(ParameterInfo(name=param_name, type=type_annotation, default=default_value))

            return parameters

        return []

    @staticmethod
    def _is_run_invocation(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "run"
        )

    @staticmethod
    def _is_name_main_guard(node: ast.AST) -> bool:
        if not isinstance(node, ast.If):
            return False
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
            return False
        if not isinstance(test.ops[0], ast.Eq):
            return False

        def is_dunder_name(value: ast.AST) -> bool:
            return isinstance(value, ast.Name) and value.id == "__name__"

        def is_main_string(value: ast.AST) -> bool:
            return isinstance(value, ast.Constant) and value.value == "__main__"

        return (is_dunder_name(test.left) and is_main_string(test.comparators[0])) or (
            is_main_string(test.left) and is_dunder_name(test.comparators[0])
        )

    @staticmethod
    def _strip_top_level_entrypoint_invocations(tree: ast.Module) -> ast.Module:
        """Remove script-style entrypoint calls before the managed runner calls run()."""
        sanitized = ast.fix_missing_locations(ast.Module(body=[], type_ignores=tree.type_ignores))
        sanitized.body = [
            node
            for node in tree.body
            if not ScriptValidator._is_run_invocation(node) and not ScriptValidator._is_name_main_guard(node)
        ]
        return ast.fix_missing_locations(sanitized)

    @staticmethod
    def parse_script(code_string: str, restricted: bool = True) -> ParsedScriptInfo:
        # 1. Parse the AST first to check for run function
        tree = ast.parse(code_string)

        # 2. Check if run function exists, and that there is exactly one
        _ = ScriptValidator._check_run_entry_point(tree)

        # 3. Extract run function parameters
        run_parameters = ScriptValidator._extract_run_function_parameters(tree)
        sanitized_tree = ScriptValidator._strip_top_level_entrypoint_invocations(copy.deepcopy(tree))

        if not restricted:
            # For non-strict mode, use regular Python compilation
            code = compile(sanitized_tree, filename="<user_script.py>", mode="exec")
            return ParsedScriptInfo(code=code, variables=run_parameters)

        # Validate the original source before compiling the sanitized runner code.
        _ = compile_restricted(  # pyright: ignore [reportUnknownVariableType]
            copy.deepcopy(tree), filename="<user_script.py>", mode="exec", policy=ScriptValidator
        )

        # 4. Compile with RestrictedPython validation (strict mode only)
        code: types.CodeType = compile_restricted(  # pyright: ignore [reportUnknownVariableType]
            sanitized_tree, filename="<user_script.py>", mode="exec", policy=ScriptValidator
        )

        return ParsedScriptInfo(code=code, variables=run_parameters)  # pyright: ignore [reportUnknownArgumentType]


@final
class SecureScriptRunner:
    """Secure runner for notte scripts"""

    UNRESTRICTED_BUILTIN_NAMES: ClassVar[tuple[str, ...]] = (
        "ArithmeticError",
        "AssertionError",
        "AttributeError",
        "BaseException",
        "EOFError",
        "Exception",
        "ImportError",
        "IndexError",
        "KeyError",
        "LookupError",
        "NameError",
        "OSError",
        "RuntimeError",
        "StopIteration",
        "SyntaxError",
        "TypeError",
        "ValueError",
        "ZeroDivisionError",
        "__build_class__",
        "abs",
        "all",
        "any",
        "ascii",
        "bin",
        "bool",
        "bytes",
        "callable",
        "chr",
        "classmethod",
        "dict",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "hasattr",
        "hash",
        "hex",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "object",
        "oct",
        "ord",
        "pow",
        "print",
        "property",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "staticmethod",
        "str",
        "sum",
        "super",
        "tuple",
        "type",
        "zip",
    )

    def __init__(self, notte_module: NotteModule):
        self.notte_module = notte_module

    def get_unrestricted_builtins(self) -> dict[str, Any]:
        allowed_builtins = {name: getattr(builtins, name) for name in self.UNRESTRICTED_BUILTIN_NAMES}
        allowed_builtins["__import__"] = self.safe_import
        allowed_builtins["open"] = self.safe_tmp_open
        return allowed_builtins

    def create_restricted_logger(self, level: str = "INFO"):  # pyright: ignore[reportUnusedParameter]
        """
        Create a restricted logger that's safe for user scripts
        """

        # Create a new logger instance to avoid conflicts
        user_logger = logger.bind(user_script=True)

        # Note: We don't remove handlers from the global logger to avoid interfering
        # with the main application logging. The user script logs will go to both
        # the main app.log file and stdout.
        return user_logger

    def _is_safe_attribute(self, attr_value: Any) -> bool:
        """
        Determine if an attribute is safe to expose
        """
        # Allow classes, functions, and basic data types
        safe_types = (
            type,  # Classes
            types.FunctionType,  # Regular functions
            types.MethodType,  # Methods
            types.BuiltinFunctionType,  # Built-in functions
            types.BuiltinMethodType,  # Built-in methods
            str,
            int,
            float,
            bool,  # Basic data types
            list,
            dict,
            tuple,
            set,  # Collections
            type(None),  # None
        )

        # Block dangerous types
        dangerous_types = (
            types.ModuleType,  # Modules could contain dangerous functions
            types.CodeType,  # Code objects
            types.FrameType,  # Frame objects
        )

        if isinstance(attr_value, dangerous_types):
            return False

        if isinstance(attr_value, safe_types):
            return True

        # Allow callable objects (like classes and functions)
        if callable(attr_value):
            return True

        # Be conservative - if we're not sure, don't allow it
        return False

    def create_restricted_notte(self):
        """
        Alternative approach: Use types.SimpleNamespace for a cleaner solution
        """

        restricted_notte = types.SimpleNamespace()

        # Copy all public attributes
        for attr_name in dir(self.notte_module):
            if not attr_name.startswith("_"):  # Only public attributes
                attr_value = getattr(self.notte_module, attr_name)
                if self._is_safe_attribute(attr_value):
                    setattr(restricted_notte, attr_name, attr_value)

        return restricted_notte

    def get_safe_globals(self) -> dict[str, Any]:
        """
        Create a safe global environment for script execution
        """
        # Start with RestrictedPython's safe globals (includes safe builtins)
        restricted_globals: dict[str, Any] = safe_globals.copy()

        # Add __import__ to __builtins__ so RestrictedPython can find it
        if "__builtins__" in restricted_globals:
            builtins_value = restricted_globals["__builtins__"]
            if isinstance(builtins_value, dict):
                builtins_value["__import__"] = self.safe_import
            else:
                # Convert __builtins__ module to dict and add __import__
                builtins_dict: dict[str, Any] = {}
                if hasattr(builtins_value, "__dict__"):
                    builtins_dict.update(builtins_value.__dict__)
                builtins_dict["__import__"] = self.safe_import
                restricted_globals["__builtins__"] = builtins_dict
        else:
            restricted_globals["__builtins__"] = {"__import__": self.safe_import}

        # Add our custom safe objects
        restricted_globals.update(
            {
                "notte": self.create_restricted_notte(),
                "logger": self.create_restricted_logger(),
                # Required guard functions for RestrictedPython
                "_getattr_": self.safe_getattr,
                "_getitem_": self.safe_getitem,
                "_getiter_": self.safe_getiter,
                "_write_": self.safe_write,
                # RestrictedPython requires these variables to be defined
                "__metaclass__": type,  # Required for RestrictedPython compiled code
                "_iter_unpack_sequence_": iter,  # Iterator unpacking guard
                "__name__": "__main__",  # Standard module name
                "__file__": "<user_script.py>",  # Standard filename
                # Import handling
                # Additional safe built-ins that might be useful
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "min": min,
                "max": max,
                "sum": sum,
                "abs": abs,
                "round": round,
                "sorted": sorted,
                "getattr": self.safe_getattr,
                "hasattr": self.safe_hasattr,
                "open": self.safe_tmp_open,
                "enumerate": enumerate,
                "zip": zip,
                "range": range,
            }
        )

        return restricted_globals

    def safe_tmp_open(self, file: Any, mode: str = "r", *args: Any, **kwargs: Any):
        """
        Restricted open() replacement that only allows access under /tmp.
        """
        if kwargs.get("opener") is not None:
            raise PermissionError("Custom openers are not allowed")

        tmp_root = Path("/tmp").resolve()
        requested_path = Path(file)
        target = requested_path if requested_path.is_absolute() else tmp_root / requested_path
        resolved_target = target.resolve(strict=False)

        if resolved_target != tmp_root and tmp_root not in resolved_target.parents:
            raise PermissionError("Only files inside /tmp are allowed")

        return builtins.open(resolved_target, mode, *args, **kwargs)

    def safe_getattr(
        self,
        obj: Any,
        name: str,
        default: Any = _GETATTR_MISSING_DEFAULT,
    ) -> Any:
        """
        Safe attribute access guard
        """
        # Block access to dangerous attributes
        dangerous_attrs = {
            "__class__",
            "__bases__",
            "__subclasses__",
            "__mro__",
            "__globals__",
            "__code__",
            "__func__",
            "__self__",
            "__dict__",
            "__getattribute__",
            "__setattr__",
            "__delattr__",
        }

        if name in dangerous_attrs:
            raise AttributeError(f"Access to attribute '{name}' is not allowed")

        if isinstance(obj, types.ModuleType):
            module_name = obj.__name__
            if name in ScriptValidator.DISALLOWED_IMPORT_MEMBERS.get(module_name, set()):
                raise AttributeError(f"Access to attribute '{module_name}.{name}' is not allowed")

        # Block access to private attributes
        if name.startswith("_"):
            raise AttributeError(f"Access to private attribute '{name}' is not allowed")

        if default is _GETATTR_MISSING_DEFAULT:
            return getattr(obj, name)

        return getattr(obj, name, default)

    def safe_hasattr(self, obj: Any, name: str) -> bool:
        """
        Safe hasattr replacement that applies the same attribute policy as safe_getattr.
        """
        missing = object()
        try:
            result = self.safe_getattr(obj, name, default=missing)
        except AttributeError:
            return False
        return result is not missing

    def safe_getitem(self, obj: Any, key: Any):
        """
        Safe item access guard
        """
        return obj[key]

    def safe_getiter(self, obj: Any):
        """
        Safe iterator guard
        """
        return iter(obj)

    def safe_write(self, obj: Any):
        """
        Safe write guard - controls what can be assigned to
        """
        return obj

    def safe_import(self, name: str, *args: Any, **kwargs: Any):
        """
        Safe import guard - only allow whitelisted modules
        """
        ScriptValidator.check_valid_import(name)

        return __import__(name, *args, **kwargs)

    def custom_import_guard(self, name: str, *args: Any, **kwargs: Any):
        """
        Custom import guard - block all imports except whitelisted ones
        DEPRECATED: Use safe_import instead
        """
        allowed_imports = {
            # You can add specific modules here if needed
            # 'math', 'datetime', 'json'
        }

        if name not in allowed_imports:
            raise ImportError(f"Import of '{name}' is not allowed")

        return __import__(name, *args, **kwargs)

    def _validate_variables(self, run_parameters: list[ParameterInfo], variables: dict[str, Any] | None) -> None:
        """
        Validate that the provided variables match the run function's expected parameters

        Also coerces collection-typed variables in place, so a string spelling
        out a list or dict arrives at the run function as the collection it
        describes. That happens here, and mutates rather than returns, because
        this is the one hook every caller already shares: the workflows Lambda
        replaces `run_script` wholesale and calls this method on the same dict it
        later splats into `run(**variables)`. A separate coercion step would be
        correct and would miss the path that actually runs published functions.

        Args:
            run_parameters: List of parameters expected by the run function
            variables: Variables to be passed to the run function

        Raises:
            ValueError: If validation fails
        """
        variables = variables or {}

        # Collect required parameters (those without defaults)
        required_params = {param.name for param in run_parameters if param.default is None}
        provided_params = set(variables.keys())
        all_params = {param.name for param in run_parameters}

        # Check for missing required parameters
        missing_required = required_params - provided_params
        if missing_required:
            raise ValueError(f"Missing required parameters for run function: {sorted(missing_required)}")

        # Check for unexpected parameters
        unexpected_params = provided_params - all_params
        if unexpected_params:
            raise ValueError(
                f"Unexpected variable names for run function: {sorted(unexpected_params)} (expected variable names: {sorted(all_params)})"
            )

        _ = coerce_collection_variables(run_parameters, variables)

        # Optional: Log parameter information for debugging
        if hasattr(self, "logger"):
            param_info: list[str] = []
            for param in run_parameters:
                type_str = f": {param.type}" if param.type else ""
                default_str = f" = {param.default}" if param.default is not None else " (required)"
                param_info.append(f"{param.name}{type_str}{default_str}")

            if param_info:
                self.create_restricted_logger().debug(f"Run function parameters: {', '.join(param_info)}")

    def run_script(self, code_string: str, variables: dict[str, Any] | None = None, restricted: bool = False) -> Any:
        """
        Run a user script with optional RestrictedPython validation

        Args:
            code_string: The Python script to execute
            variables: Variables to pass to the run function
            restricted: If True, use RestrictedPython for safety (default: False)
                   If False, use regular Python execution (full access)
        """
        # Parse the script to get code and parameter information
        parsed_info = ScriptValidator.parse_script(code_string, restricted=restricted)

        # Validate variables against run function parameters
        self._validate_variables(parsed_info.variables, variables)

        if restricted:
            # Use RestrictedPython for strict mode
            execution_globals = self.get_safe_globals()
            result: dict[str, object] = {}

            try:
                exec(parsed_info.code, execution_globals, result)
                execution_globals.update(
                    {name: value for name, value in result.items() if name not in execution_globals}
                )

                # Call the run function if it exists
                run_ft = result.get("run")
                if run_ft is None or not callable(run_ft):
                    raise MissingRunFunctionError("Script must contain a 'run' function")
                if callable(run_ft):
                    return run_ft(**variables) if variables else run_ft()

                return result

            except Exception:
                raise RuntimeError(f"Python script execution failed in restricted mode: {traceback.format_exc()}")
        else:
            # Use regular Python execution for non-strict mode
            # Create execution namespace with notte module and logger
            execution_globals: dict[str, Any] = {
                "__name__": "__main__",
                "__package__": None,
                "__builtins__": self.get_unrestricted_builtins(),
                "notte": self.notte_module,
                "logger": self.create_restricted_logger(),
                "open": self.safe_tmp_open,
            }

            try:
                # Execute the script in regular Python
                exec(parsed_info.code, execution_globals)

                # Call the run function
                run_ft = execution_globals.get("run")
                if run_ft is None or not callable(run_ft):
                    raise MissingRunFunctionError("Python script must contain a 'run' function")
                if callable(run_ft):
                    return run_ft(**variables) if variables else run_ft()

                return execution_globals

            except Exception:
                raise RuntimeError(f"Script execution failed in unrestricted mode: {traceback.format_exc()}")
