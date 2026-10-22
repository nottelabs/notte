"""The runtime bridge stays isolated from v2 implementation and generated APIs."""

import ast
import importlib
import inspect
import pathlib
import pickle
import subprocess
import sys
import warnings
from unittest.mock import Mock

import pytest
from notte_core import _v1_aliases as core
from notte_sdk import NotteClient
from notte_sdk import _v1_aliases as sdk
from notte_sdk.endpoints.functions import NotteFunction

from tests.sdk.test_functions_codegen import FUNCTION, RUN
from tests.sdk.test_generated_endpoints import fake
from tests.sdk.test_personas_codegen import EMAIL, SMS
from tests.sdk.test_vaults_codegen import CARD, CREDS
from tests.sdk.test_vaults_codegen import client as capture_client

client = capture_client

# A surviving public name for every old module path, including partially retired modules.
SYMBOLS = {
    "errors.actions": "ActionExecutionError",
    "errors.base": "NotteBaseError",
    "errors.llm": "LLMParsingError",
    "errors.processing": "ScrapeFailedError",
    "errors.provider": "LLMProviderError",
    "common": "AsyncResource",
    "common.config": "NotteConfig",
    "common.logging": "logger",
    "common.cache": "CacheDirectory",
    "common.resource": "AsyncResource",
    "common.telemetry": "track_usage",
    "common.types": "TResponseFormat",
    "browser.observation": "ExecutionResult",
    "browser.dom_tree": "DomNode",
    "browser.highlighter": "BoundingBox",
    "browser.node_type": "NodeType",
    "browser.snapshot": "BrowserSnapshot",
    "data.fetch": "FetchData",
    "data.space": "StructuredData",
    "ast": "ParameterInfo",
    "utils.files": "create_or_append_cookies_to_file",
    "utils.image": "image_from_bytes",
    "utils.pydantic_schema": "JsonResponseFormat",
    "utils.raw_file": "get_filename",
    "utils.singleton": "Singleton",
    "utils.url": "clean_url",
}


@pytest.mark.parametrize("old,new", core._MODULE_ALIASES.items())
def test_import_alias(old: str, new: str, monkeypatch: pytest.MonkeyPatch) -> None:
    alias = importlib.import_module(old)
    monkeypatch.setattr(alias, "_warned", False)
    symbol = SYMBOLS[old.removeprefix("notte_core.")]
    target = importlib.import_module(new)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert getattr(alias, symbol) is getattr(target, symbol)
        for name in core._PUBLIC_NAMES[old]:
            assert getattr(alias, name) is getattr(target, name)
        assert getattr(alias, symbol) is getattr(target, symbol)
    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert new in str(caught[0].message)
    assert "removed in notte 2.0" in str(caught[0].message)
    assert set(alias.__all__) <= set(dir(alias))
    monkeypatch.setattr(alias, "_warned", False)
    namespace: dict[str, object] = {}
    with warnings.catch_warnings(record=True) as wildcard_warnings:
        warnings.simplefilter("always")
        exec(f"from {old} import *", namespace)
    assert len(wildcard_warnings) == 1
    for name in alias.__all__:
        assert namespace[name] is getattr(alias, name)
    assert inspect.ismodule(alias)
    assert not hasattr(alias, "__file__")
    with pytest.raises(ImportError):
        exec(f"from {old} import ThisNameNeverExisted", {})


def test_tables_cover_every_entry() -> None:
    assert {"notte_core." + name for name in SYMBOLS} == core._MODULE_ALIASES.keys()
    assert {old for aliases in sdk._RENAMED_METHODS.values() for old in aliases} == CASES.keys()


@pytest.mark.parametrize("old,names", core._STDLIB_REEXPORTS.items())
def test_only_recorded_stdlib_reexports(old: str, names: dict[str, str]) -> None:
    alias = importlib.import_module(old)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for name, module in names.items():
            assert getattr(alias, name) is importlib.import_module(module)
    assert not hasattr(alias, "this_is_not_a_stdlib_module")
    if old == "notte_core.common.config":
        with pytest.raises(ImportError):
            exec("from notte_core.common.config import fractions", {})


def test_inspection_pickle_and_real_parents() -> None:
    import notte_core.data
    import notte_core.errors
    from notte_core.errors.actions import ActionExecutionError

    assert notte_core.errors.__file__.endswith("errors.py")
    assert not hasattr(notte_core.errors, "__path__")
    assert notte_core.data.__file__.endswith("data.py")
    assert not hasattr(notte_core.data, "__path__")
    assert pickle.loads(pickle.dumps(ActionExecutionError)) is ActionExecutionError
    assert inspect.getmodule(ActionExecutionError) is notte_core.errors
    assert inspect.getmembers(sys.modules["notte_core.errors.actions"])


def test_imports_stay_lazy_in_fresh_process() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
import notte_core
assert 'notte_core.observation' not in sys.modules
assert 'notte_core.config' not in sys.modules
assert 'notte_core.types' not in sys.modules
assert 'notte_core.data' in sys.modules
assert 'pydantic' not in sys.modules
import notte_core.data.fetch
from notte_core.fetch import FetchData
assert notte_core.data.fetch.FetchData is FetchData
from notte_core.common.config import os
assert os is sys.modules['os']
from notte_sdk import NotteClient
# Sphinx scans live sys.modules values for unresolved annotation strings.
before = set(sys.modules)
for module in sys.modules.values():
    hasattr(module, 'strNone')
assert set(sys.modules) == before
""",
        ],
        check=True,
    )


CASES = {
    "get_credentials": ("vaults", ("vault",), {"url": "https://example.com"}, {"credentials": CREDS}),
    "list_credentials": ("vaults", (), {"vault_id": "vault"}, {"credentials": []}),
    "add_or_update_credentials": ("vaults", ("vault",), {"url": "https://example.com", **CREDS}, {"status": "success"}),
    "delete_credentials": ("vaults", ("vault",), {"url": "https://example.com"}, {"status": "success"}),
    "get_credit_card": ("vaults", ("vault",), {}, {"credit_card": CARD}),
    "set_credit_card": ("vaults", ("vault",), CARD, {"status": "success"}),
    "delete_credit_card": ("vaults", ("vault",), {}, {"status": "success"}),
    "list_emails": ("personas", (), {"persona_id": "persona", "limit": 2}, [EMAIL]),
    "list_sms": ("personas", ("persona",), {"only_unread": True}, [SMS]),
    "get": ("functions", (), {"function_id": "fn", "version": "v1"}, {**FUNCTION, "url": "https://example.com/code"}),
    "get_run": ("functions", (), {"function_id": "fn", "run_id": "run"}, RUN),
    "run": (
        "functions",
        ("run",),
        {"function_id": "fn", "stream": False, "variables": {"x": 1}},
        {**RUN, "status": "closed", "result": "ok", "session_id": None},
    ),
    "stop_run": ("functions", ("fn", "run"), {}, {**RUN, "status": "stopped"}),
    "update_run": ("functions", ("fn", "run"), {"status": "active"}, {**RUN, "status": "updated"}),
    "auth_status": ("sessions", (), {"session_id": "session"}, {"session_id": "session", "status": "active"}),
}


@pytest.mark.parametrize(
    "cls,old,new", [(cls, old, new) for cls, aliases in sdk._RENAMED_METHODS.items() for old, new in aliases.items()]
)
def test_method_alias_transport(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, cls: type, old: str, new: str
) -> None:
    resource, args, kwargs, payload = CASES[old]
    obj = getattr(client, resource)
    transport = fake(monkeypatch, payload)
    expected = getattr(obj, new)(*args, **kwargs)
    canonical = Mock(wraps=getattr(obj, new))
    monkeypatch.setattr(obj, new, canonical)
    monkeypatch.setattr(sdk, "_warned", set())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert getattr(obj, old)(*args, **kwargs) == expected
        assert getattr(obj, old)(*args, **kwargs) == expected
    assert canonical.call_count == 2
    canonical.assert_called_with(*args, **kwargs)
    assert len(caught) == 1
    assert caught[0].category is DeprecationWarning
    assert f"{cls.__name__}.{new}" in str(caught[0].message)
    assert "removed in notte 2.0" in str(caught[0].message)
    if old != "run":
        assert transport.calls[0] == transport.calls[1] == transport.calls[2]


@pytest.mark.parametrize(
    "cls,old,new", [(cls, old, new) for cls, aliases in sdk._RENAMED_ATTRS.items() for old, new in aliases.items()]
)
def test_attribute_alias(client: NotteClient, monkeypatch: pytest.MonkeyPatch, cls: type, old: str, new: str) -> None:
    sentinel = object()
    obj = client if cls is NotteClient else object.__new__(NotteFunction)
    monkeypatch.setattr(obj if old == "workflows" else cls, new, sentinel, raising=False)
    monkeypatch.setattr(sdk, "_warned", set())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert callable(getattr(obj, old)) if old == "Workflow" else getattr(obj, old) is sentinel
        getattr(obj, old)
    assert len(caught) == 1
    assert new in str(caught[0].message)


def test_workflow_constructor_keywords(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, {**FUNCTION, "url": "https://example.com/code"})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert client.Workflow(workflow_id="fn")._function_id == "fn"
        assert client.Workflow("fn")._function_id == "fn"
        function = client.Workflow("fn")
        assert function.workflow_id == function.function_id == "fn"
        with pytest.raises(ValueError, match="different values"):
            client.Workflow(workflow_id="a", function_id="b")
        create = Mock(return_value=Mock(function_id="fn"))
        monkeypatch.setattr(client.functions, "create", create)
        client.Workflow(workflow_path="script.py")
        create.assert_called_once_with(path="script.py")


def test_dropped_local_keyword(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    function = client.Function("fn")
    run = Mock(return_value=object())
    original = next(iter(sdk._DROPPED_KWARGS))
    wrapped = sdk._drop_kwargs(run, {"local": False})
    run.__qualname__ = original.__qualname__
    monkeypatch.setattr(sdk, "_warned", set())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert wrapped(function, local=False, url="https://example.com") is run.return_value
        wrapped(function, local=False)
    assert len(caught) == 1
    assert "without `local`" in str(caught[0].message)
    assert "removed in notte 2.0" in str(caught[0].message)
    assert "local" not in run.call_args.kwargs
    with pytest.raises(ValueError, match="local execution was removed in notte 1.10"):
        function.run(local=True)
    monkeypatch.setattr(client.functions, "create_run", Mock(return_value=Mock(function_run_id="run")))
    result = Mock(status="closed", session_id=None)
    remote = Mock(return_value=result)
    monkeypatch.setattr(client.functions, "run_start", remote)
    fake(monkeypatch, {**FUNCTION, "url": "https://example.com/code"})
    monkeypatch.setattr(sdk, "_warned", set())
    with pytest.warns(DeprecationWarning, match="without `local`"):
        assert function.run(local=False, url="https://example.com") is result
    assert remote.call_args.kwargs["variables"] == {"url": "https://example.com"}
    assert NotteFunction.run.__wrapped__ is original
    assert inspect.signature(NotteFunction.run) == inspect.signature(original)


def test_v2_never_uses_v1_aliases() -> None:
    root = pathlib.Path(__file__).resolve().parents[2]
    old_modules = set(core._MODULE_ALIASES)
    activation_count = 0
    for path in root.glob("packages/*/src/**/*.py"):
        if path.name == "_v1_aliases.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert not any(
                    alias.name in old_modules or alias.name.endswith("._v1_aliases") for alias in node.names
                ), path
            elif isinstance(node, ast.ImportFrom):
                assert node.module not in old_modules, path
                assert not (node.module or "").endswith("._v1_aliases"), path
                if any(alias.name == "_v1_aliases" for alias in node.names):
                    assert path in [
                        root / f"packages/notte-{pkg}/src/notte_{pkg}/__init__.py" for pkg in ("core", "sdk")
                    ]
                    activation_count += 1
                for alias in node.names:
                    assert f"{node.module}.{alias.name}" not in old_modules, path
    assert activation_count == 2
