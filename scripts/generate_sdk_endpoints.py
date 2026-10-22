#!/usr/bin/env python3
"""Generate SDK resource operations from the committed OpenAPI snapshot.

Resource models resolve through the upstream-generated schema index. Only shared
page-operation factories and health remain in `_generated/endpoints.py`; they retain
core domain identity. See docs/design/sdk-codegen.md for ownership and compatibility.

    uv run --no-sync python scripts/generate_sdk_endpoints.py
    uv run --no-sync python scripts/generate_sdk_endpoints.py --check
    uv run --no-sync python scripts/generate_sdk_endpoints.py --check --against URL
"""

from __future__ import annotations

import argparse
import ast
import difflib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from notte_core import types as wire_types
from pydantic import AliasChoices, BaseModel
from pydantic.fields import FieldInfo
from typing_extensions import override

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.openapi_contract import download  # noqa: E402

SNAPSHOT = REPO_ROOT / "openapi" / "openapi.json"
SDK_SRC = REPO_ROOT / "packages" / "notte-sdk" / "src" / "notte_sdk"
OUTPUT = SDK_SRC / "_generated" / "endpoints.py"

# Shared page factories; resource core ownership is declared separately below.
# Values are (body model, response model); None means an untyped/no body or response.
CORE_OPERATIONS = {
    "health_check": (None, None),
    "page_execute": (None, "ExecutionResultResponse"),
    "page_observe": ("ObserveRequest", "ObserveResponse"),
    "page_scrape": ("ScrapeRequest", "ScrapeResponse"),
    "page_screenshot": (None, None),
    "scrape_webpage": (None, "ScrapeResponse"),
}

NAMING = cast(dict[str, dict[str, Any]], json.loads((REPO_ROOT / "openapi/resources.json").read_text()))


def check_naming(spec: dict[str, Any]) -> None:
    ids = {op.op_id for op in _parse(spec)}
    if missing := ids - NAMING.keys():
        raise GenerationError(f"Unmapped operations: {sorted(missing)}")
    if stale := NAMING.keys() - ids:
        raise GenerationError(f"Stale operation mappings: {sorted(stale)}")
    names: set[tuple[str, str]] = set()
    for entry in NAMING.values():
        if entry.get("exclude"):
            continue
        for key in [
            (entry["resource"], entry["method"]),
            *((a["resource"], a["method"]) for a in entry.get("aliases", [])),
        ]:
            if key in names:
                raise GenerationError(f"Duplicate resource method: {key}")
            names.add(key)


def snake_case(method: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", method).lower()


# Headers the client sets on every request (BaseClient.headers), so they are not parameters.
CLIENT_HEADERS = {"authorization", "x-notte-request-origin", "x-notte-sdk-version", "x-db-preview"}

# The clients call the generated factories as `api.<operation>(...)`, or `page_api.<operation>(...)`
# for the shared page factories of this module.
USAGE_PATTERN = re.compile(r"\b(?:page_)?api\.([a-z_][a-z0-9_]*)\(")

METHOD_ORDER = {"get": 0, "post": 1, "put": 2, "patch": 3, "delete": 4}

JsonObject = dict[str, Any]


class GenerationError(ValueError):
    pass


@dataclass(frozen=True)
class Binding:
    """A model bound to a schema: `alias.name` in the generated module."""

    alias: str
    name: str
    model: type[BaseModel]

    @property
    def ref(self) -> str:
        return f"{self.alias}.{self.name}"


@dataclass
class Operation:
    op_id: str
    method: str
    path: str
    tag: str
    summary: str
    description: str
    path_params: list[str]
    query_params: dict[str, bool]  # name -> required
    header_params: dict[str, bool]
    body_schema: str | None = None
    body_content_type: str | None = None
    body_required: bool = False
    response_shape: str = "object"  # object | array | page | none | untyped | binary
    response_schema: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.op_id.lstrip("_")


def _ref_name(schema: JsonObject) -> str | None:
    ref = schema.get("$ref")
    return ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None


def _parse(spec: JsonObject) -> list[Operation]:
    operations: list[Operation] = []
    for path, item in cast(JsonObject, spec["paths"]).items():
        for method, raw in cast(JsonObject, item).items():
            if method not in METHOD_ORDER:
                continue
            op = cast(JsonObject, raw)
            params = cast(list[JsonObject], op.get("parameters", []))
            operation = Operation(
                op_id=cast(str, op["operationId"]),
                method=method.upper(),
                path=path,
                tag=cast(list[str], op.get("tags", ["untagged"]))[0],
                summary=cast(str, op.get("summary", "")).strip(),
                description=cast(str, op.get("description", "")).strip(),
                path_params=re.findall(r"\{(\w+)\}", path),
                query_params={p["name"]: bool(p.get("required")) for p in params if p["in"] == "query"},
                header_params={
                    p["name"]: bool(p.get("required"))
                    for p in params
                    if p["in"] == "header" and p["name"].lower() not in CLIENT_HEADERS
                },
            )
            if op.get("deprecated"):
                operation.notes.append("Deprecated by the API.")
            body = cast(JsonObject, op.get("requestBody", {}))
            if content := cast(JsonObject, body.get("content", {})):
                content_type = next(iter(content))
                operation.body_content_type = content_type
                operation.body_schema = _ref_name(cast(JsonObject, content[content_type].get("schema", {})))
                operation.body_required = bool(body.get("required"))
            _parse_response(operation, cast(JsonObject, op.get("responses", {})))
            operations.append(operation)
    operations.sort(key=lambda o: (o.tag, o.path, METHOD_ORDER[o.method.lower()]))
    return operations


def _parse_response(operation: Operation, responses: JsonObject) -> None:
    success = sorted(code for code in responses if code.startswith("2"))
    if not success:
        operation.response_shape = "none"
        return
    content = cast(JsonObject, cast(JsonObject, responses[success[0]]).get("content", {}))
    if "application/json" not in content:
        operation.response_shape = "binary" if content else "none"
        return
    if "application/octet-stream" in content:
        operation.response_shape = "binary"
        return
    schema = cast(JsonObject, content["application/json"].get("schema", {}))
    if (name := _ref_name(schema)) is not None:
        if name.startswith("PaginatedResponse_") and name.endswith("_"):
            operation.response_shape, operation.response_schema = "page", name[len("PaginatedResponse_") : -1]
        else:
            operation.response_shape, operation.response_schema = "object", name
    elif schema.get("type") == "array" and (item := _ref_name(cast(JsonObject, schema.get("items", {})))):
        operation.response_shape, operation.response_schema = "array", item
    else:
        operation.response_shape = "untyped"


def _wire_names(name: str, info: FieldInfo) -> set[str]:
    """The keys a field reads: its name, alias and validation aliases (as openapi_contract matches them)."""
    alias = info.validation_alias
    choices = alias.choices if isinstance(alias, AliasChoices) else [alias] if alias is not None else []
    return {name, *([info.alias] if info.alias else []), *(c for c in choices if isinstance(c, str))}


def _check_fields(what: str, binding: Binding, schema: JsonObject | None) -> None:
    if schema is None:
        return
    props = cast(JsonObject, schema.get("properties", {}))
    fields = binding.model.model_fields
    if missing := [
        name for name, info in fields.items() if info.is_required() and not _wire_names(name, info) & props.keys()
    ]:
        raise GenerationError(f"{what}: {binding.name} requires fields the schema lacks: {missing}")


@dataclass
class Bound:
    operation: Operation
    body: Binding | None
    response: Binding | None
    query: Binding | None
    # Multipart file fields: schema property -> public keyword (a local path).
    files: dict[str, str] = field(default_factory=dict)
    # Shared page operations call the core-bound `page_api` factories (see PAGE_OPERATIONS).
    page: bool = False


def _bind(spec: JsonObject, operations: list[Operation], strict: bool) -> list[Bound]:
    """Retain core identity only for the explicitly shared page-operation group."""
    by_name = {op.name: op for op in operations}
    result: list[Bound] = []
    for name, (body_name, response_name) in CORE_OPERATIONS.items():
        if name not in by_name:
            if strict:
                raise GenerationError(f"Shared operation {name} is absent from the spec")
            continue
        op = by_name[name]
        bindings: list[Binding | None] = []
        try:
            for model_name, schema in ((body_name, op.body_schema), (response_name, op.response_schema)):
                binding = Binding("wire", model_name, getattr(wire_types, model_name)) if model_name else None
                if binding is not None and schema is not None:
                    _check_fields(name, binding, spec["components"]["schemas"].get(schema))
                bindings.append(binding)
        except GenerationError:
            if strict:
                raise
            continue
        result.append(Bound(op, bindings[0], bindings[1], None))
    return result


def _docstring(bound: Bound) -> list[str]:
    op = bound.operation
    lines = [f"{op.summary or op.name} (`{op.method} {op.path}`)."]
    notes = list(op.notes)
    if op.body_content_type is not None and bound.body is None:
        what = f"`{op.body_schema}`" if op.body_schema else "an inline schema"
        notes.append(f"Body: {what} ({op.body_content_type}) has no model in notte_core.")
    elif op.body_content_type == "multipart/form-data":
        notes.append("Body: multipart/form-data, attach files with `BaseClient.request_upload`.")
    if op.query_params and bound.query is None:
        names = ", ".join(f"{name}{' (required)' if req else ''}" for name, req in op.query_params.items())
        notes.append(f"Query: {names}.")
    elif bound.query is not None and (rest := [p for p in op.query_params if p not in bound.query.model.model_fields]):
        notes.append(f"Query parameters not in `{bound.query.name}`: {', '.join(rest)}.")
    for name, required in op.header_params.items():
        notes.append(
            f"Header `{name}`{' (required)' if required else ''}: pass it to `BaseClient.request(headers=...)`."
        )
    match op.response_shape:
        case "array":
            notes.append("Responds with a JSON array: use `BaseClient.request_list`.")
        case "page":
            notes.append("Responds with a page (`items`): use `BaseClient.request_list`.")
        case "none":
            notes.append("Responds with no content.")
        case "binary":
            notes.append("Responds with a file: read it with `BaseClient.request_bytes` or `stream_bytes`.")
        case "untyped":
            notes.append("Responds with an untyped body (no schema): parsed as `RawResponse`.")
        case _:
            pass
    if op.response_schema is not None and bound.response is None:
        notes.append(f"Response schema `{op.response_schema}` has no model in notte_core: parsed as `RawResponse`.")
    elif bound.response is not None and op.response_schema not in (None, bound.response.name):
        notes.append(f"Parses response schema `{op.response_schema}` with `{bound.response.name}`.")
    if not notes:
        return lines
    return [*lines, "", *notes]


def _render_operation(bound: Bound) -> str:
    op = bound.operation
    response = bound.response.ref if bound.response is not None else "RawResponse"
    args = [f"{name}: str," for name in op.path_params]
    if op.body_content_type is not None:
        body_type = bound.body.ref if bound.body is not None else "BaseModel"
        args.append(f"body: {body_type}," if op.body_required else f"body: {body_type} | None = None,")
    if op.query_params:
        query_type = bound.query.ref if bound.query is not None else "BaseModel"
        args.append("*,")
        if any(op.query_params.values()):
            args.append(f"params: {query_type},")
        else:
            args.append(f"params: {query_type} | None = None,")
    if args:
        signature = [f"def {op.name}(", *(f"    {arg}" for arg in args), f") -> NotteEndpoint[{response}]:"]
    else:
        signature = [f"def {op.name}() -> NotteEndpoint[{response}]:"]

    path = op.path
    for name in op.path_params:
        path = path.replace(f"{{{name}}}", f"{{_segment({name})}}")
    path_literal = f'f"{path}"' if op.path_params else f'"{path}"'

    doc = _docstring(bound)
    if len(doc) == 1:
        docstring = [f'    """{doc[0]}"""']
    else:
        docstring = [f'    """{doc[0]}', *(f"    {line}" if line else "" for line in doc[1:]), '    """']

    call = [
        "    return NotteEndpoint(",
        f'        method="{op.method}",',
        f"        path={path_literal},",
        f"        response={response},",
    ]
    if op.body_content_type is not None:
        call.append("        request=body,")
    if op.query_params:
        call.append("        params=params,")
    call.append("    )")
    return "\n".join([*signature, *docstring, *call])


HEADER = '''\
# Generated by scripts/generate_sdk_endpoints.py from openapi/openapi.json ({title} {version}).
# Do not edit: run `make sdk-endpoints` after changing the snapshot, the bindings or the models.
# The clients import this module and endpoints.base imports the client for typing (as in client.py):
# pyright: reportImportCycles=false
"""Shared page-operation factories and health; resource factories live in operations.py.

Page bodies/responses retain notte_core domain identity for local/cloud interoperability.
Hand-written PageClient behavior is unchanged. Do not add core-bound resource factories here.
"""

from __future__ import annotations

from urllib.parse import quote

from notte_core import types as wire
from pydantic import BaseModel

from notte_sdk.endpoints.base import NotteEndpoint, RawResponse


def _segment(value: str) -> str:
    """Encode a path parameter as a single path segment."""
    return quote(value, safe="")
'''


def render(spec: JsonObject, strict: bool = True) -> tuple[str, dict[str, str]]:
    """The generated module, and each operation's code by name."""
    bound = _bind(spec, _parse(spec), strict)
    info = cast(JsonObject, spec.get("info", {}))
    blocks: dict[str, str] = {}
    parts = [HEADER.format(title=info.get("title", "API"), version=info.get("version", "?"))]
    tag: str | None = None
    for item in bound:
        if item.operation.name in blocks:
            raise GenerationError(f"two operations are named {item.operation.name}")
        code = _render_operation(item)
        blocks[item.operation.name] = code
        section = f"# {item.operation.tag}\n" if item.operation.tag != tag else ""
        tag = item.operation.tag
        parts.append(f"\n\n{section}{code}\n")
    text = "".join(parts)
    if "BaseModel" not in "".join(blocks.values()):
        text = text.replace("from pydantic import BaseModel\n", "")
    return text, blocks


def used_operations() -> dict[str, list[str]]:
    """Operations the hand-written SDK calls, with the files that call them."""
    used: dict[str, list[str]] = {}
    for source in sorted(SDK_SRC.rglob("*.py")):
        if source == OUTPUT:
            continue
        for name in USAGE_PATTERN.findall(source.read_text()):
            used.setdefault(name, []).append(str(source.relative_to(SDK_SRC)))
    return used


def _check_against(url: str, committed: dict[str, str]) -> int:
    """Release gate: every operation the SDK calls must be the same in the live API."""
    live_spec = download(url)
    _, live = render(live_spec, strict=False)
    committed = {**committed, **migrated_contracts(json.loads(SNAPSHOT.read_text()))}
    live.update(migrated_contracts(live_spec))
    failures = 0
    for name in sorted(used_operations()):
        if name not in live:
            print(f"{name}: called by the SDK but not served by {url}", file=sys.stderr)
            failures += 1
        elif committed.get(name) != live[name]:
            diff = difflib.unified_diff(
                committed.get(name, "").splitlines(), live[name].splitlines(), "snapshot", url, lineterm=""
            )
            print(f"{name}: differs in {url}\n" + "\n".join(diff), file=sys.stderr)
            failures += 1
    if failures:
        return 1
    print(f"The {len(used_operations())} operations the SDK calls match {url}.")
    return 0


@cache
def _generated_models() -> ModuleType:
    # Load the data-only file without importing notte_sdk.__init__ and its clients.
    # Generation must work even when resource output is missing or stale.
    spec = importlib.util.spec_from_file_location("_sdk_codegen_models", SDK_SRC / "_generated/models.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Resource:
    name: str
    # (operation, Python method name): the table's method and its aliases, in snake_case.
    methods: tuple[tuple[str, str], ...]
    client_path: str = ""

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(operation for operation, _ in self.methods))


def _group(operation: str, resource: str) -> str:
    return "RunPayloads" if operation == "prepare_run_payload_upload" else resource.title()


def _members(name: str) -> tuple[tuple[str, str], ...]:
    members: list[tuple[str, str]] = []
    for operation, entry in NAMING.items():
        if entry.get("exclude"):
            continue
        # `pythonImplementation` keeps the primary method hand-written; aliases are still generated.
        targets = [] if entry.get("pythonImplementation") else [(entry["resource"], entry["method"])]
        targets += [(alias["resource"], alias["method"]) for alias in entry.get("aliases", [])]
        members.extend(
            (operation, snake_case(method)) for resource, method in targets if _group(operation, resource) == name
        )
    return tuple(members)


# Resource membership comes exclusively from the shared operation table. The one
# payload mixin avoids a runtime import cycle in multipart/payload conveniences.
RESOURCES = tuple(
    Resource(name, _members(name), path)
    for name, path in (
        ("RunPayloads", ""),
        ("Functions", "functions"),
        ("Sessions", ""),
        ("Files", "sessions"),
        ("Personas", "personas"),
        ("Profiles", "profiles"),
        ("Vaults", "vaults"),
    )
)
# Every mapped operation gets a factory in operations.py, including the ones whose
# primary method is hand-written, so no client spells out a path the spec describes.
# Shared page operations reuse the core-bound factories of endpoints.py instead.
PAGE_OPERATIONS = {
    # operation: (core body model and keywords, or the positional body type)
    "page_observe": ("ObserveRequest", "ObserveRequestDict"),
    "page_scrape": ("ScrapeRequest", "ScrapeRequestDict"),
    "page_execute": ("actions.BaseAction", None),
}


def _factories(name: str) -> tuple[str, ...]:
    """Operations whose factory is emitted with resource `name` (their primary resource)."""
    return tuple(
        operation
        for operation, entry in NAMING.items()
        if not entry.get("exclude")
        and operation not in PAGE_OPERATIONS
        and _group(operation, entry["resource"]) == name
    )


# Multipart file fields are sent from a local path; these keep their public keyword.
FILE_KEYWORDS = {"BodyFunctionCreateFunctionsPost": {"file": "path"}}
# Behavior-rich types keep their core identity. Request serialization bypasses
# business validators; openapi_contract.py guards these core/schema bindings.
CORE_MODELS = {
    name: name
    for name in (
        "AddCredentialsRequest",
        "AddCreditCardRequest",
        "GetCredentialsResponse",
        "GetCreditCardResponse",
        "Credential",
        "ListCredentialsResponse",
    )
}
MODEL_OVERRIDES = {
    **{
        schema: ("core", public)
        for schema, public in {
            "ApiSessionStartRequest": "SessionStartRequest",
            "SessionResponse": "SessionResponse",
            "SessionDebugResponse": "SessionDebugResponse",
            "ListSessionsParametersQuery": "SessionListRequest",
            "ManagedAuthReadiness": "SessionAuthResponse",
            "ReplayResponse": "ReplayResponse",
            "BodySessionCookiesSetSessionsSessionIdCookiesPost": "SetCookiesRequest",
            "ExecutionResponse": "SetCookiesResponse",
            "Cookie": "Cookie",
            "SessionProfile": "SessionProfile",
            "NotteProxy": "NotteProxy",
            "ExternalProxy": "ExternalProxy",
            "GetCookiesResponse": "GetCookiesResponse",
        }.items()
    },
    **{
        schema: ("core", public)
        for schema, public in {
            "FunctionResponse": "GetFunctionResponse",
            "FunctionWithLinkResponse": "GetFunctionWithLinkResponse",
            "PaginatedResponseFunctionListItemResponse": "ListFunctionsResponse",
            "GetFunctionRunResponse": "GetFunctionRunResponse",
            "FunctionRunListItemResponse": "FunctionRunListItemResponse",
            "PaginatedResponseFunctionRunListItemResponse": "ListFunctionRunsResponse",
            "UpdateFunctionRunResponse": "UpdateFunctionRunResponse",
            "ListFunctionsParametersQuery": "ListFunctionsRequest",
            "ListFunctionRunsByFunctionIdParametersQuery": "ListFunctionRunsRequest",
            "FunctionDownloadUrlParametersQuery": "GetFunctionRequest",
        }.items()
    },
    "SessionProfilePreviewResponse": ("nested_models", "SessionProfilePreviewResponse"),
    "RunPayloadUploadResponse": ("run_payloads_compat", "UploadResponse"),
    "ListPersonasParametersQuery": ("core", "PersonaListRequest"),
    "EmailResponse": ("core", "EmailResponse"),
    "PersonaSmsListParametersQuery": ("models", "PersonaEmailsListParametersQuery"),
    **{name: ("core", public) for name, public in CORE_MODELS.items()},
    "ListVaultsParametersQuery": ("core", "VaultListRequest"),
    "ProfileDeleteResponse": ("profiles_compat", "ProfileDeleteResponse"),
    "ProfileResponse": ("profiles_compat", "ProfileResponse"),
    "ProfileListParametersQuery": ("profiles_compat", "ProfileListRequest"),
}
KEYWORD_NAMES = {
    "ApiSessionStartRequest": "SessionStartRequestDict",
    "ListSessionsParametersQuery": "SessionListRequestDict",
    "SessionStopParametersQuery": "SessionStopRequestDict",
    "BodySessionCookiesSetSessionsSessionIdCookiesPost": "SetCookiesRequestDict",
    "SessionProfile": "SessionProfileDict",
    "NotteProxy": "NotteProxyDict",
    "ExternalProxy": "ExternalProxyDict",
    "TailnetProxy": "TailnetProxyDict",
    "BodyFunctionCreateFunctionsPost": "CreateFunctionRequestDict",
    "BodyUploadSessionFileSessionsSessionIdFilesPost": "UploadSessionFileRequestDict",
    "FunctionUpdateParametersQuery": "UpdateFunctionRequestDict",
    "ListFunctionsParametersQuery": "ListFunctionsRequestDict",
    "ListFunctionRunsByFunctionIdParametersQuery": "ListFunctionRunsRequestDict",
    "FunctionDownloadUrlParametersQuery": "GetFunctionRequestDict",
    "ListPersonasParametersQuery": "PersonaListRequestDict",
    "PersonaEmailsListParametersQuery": "MessageReadRequestDict",
    "PersonaSmsListParametersQuery": "MessageReadRequestDict",
    "VaultCredentialsGetParametersQuery": "GetCredentialsRequestDict",
    "VaultCredentialsDeleteParametersQuery": "DeleteCredentialsRequestDict",
    "ListVaultsParametersQuery": "VaultListRequestDict",
    "CredentialsDictInput": "CredentialsDict",
    "CreditCardDictInput": "CreditCardDict",
    "ProfileCreateRequest": "ProfileCreateRequestDict",
    "ProfileListParametersQuery": "ProfileListRequestDict",
}
KEYWORD_ANNOTATIONS = {
    "PersonaCreateRequest": {"email_provider": 'Literal["notte", "agentmail", "resend"]'},
    "ApiSessionStartRequest": {
        "browser_type": "config.BrowserType",
        "proxies": "list[core.ProxySettings] | list[ProxySettingsDict] | bool | core.ProxyGeolocationCountry | core.ProxyGeolocationCountryCode",
        "viewport_width": "int | None",
        "viewport_height": "int | None",
        "profile": "SessionProfileDict | core.SessionProfile | None",
        "auth_ids": "list[str]",
    },
    "NotteProxy": {"country": "core.ProxyGeolocationCountry | None"},
    "ProfileStateImportRequest": {"domains": "list[str] | None"},
    "ListSessionsParametersQuery": {"include_system": "bool | None"},
    "SessionStopParametersQuery": {"close_reason": 'Literal["manual", "error"]'},
    "BodySessionCookiesSetSessionsSessionIdCookiesPost": {"cookies": "list[core.Cookie] | list[config.CookieDict]"},
    "FunctionRunGetMetadataParametersQuery": {"payload_mode": "str"},
    "FunctionRunUpdateRequest": {
        "logs": "list[str] | None",
        "result": "Any | None",
        "status": 'Literal["closed", "active", "failed"]',
    },
    "ListSessionFilesParametersQuery": {"source": "str | None"},
}
KEYWORD_DOCSTRINGS = {
    "SessionStartRequestDict": 'Request dictionary for starting a session.\n\nArgs:\n    solve_captchas: Whether to try to automatically solve captchas\n    max_duration_minutes: Maximum session lifetime in minutes (absolute maximum).\n    idle_timeout_minutes: Idle timeout in minutes. Session closes after this period of inactivity.\n    proxies: List of custom proxies to use for the session. If True, the default proxies will be used.\n    browser_type: The browser type to use. Can be chromium or chrome.\n    user_agent: The user agent to use for the session\n    chrome_args: Overwrite the chrome instance arguments\n    viewport_width: The width of the viewport\n    viewport_height: The height of the viewport\n    aspect_ratio: Viewport shape preset ("5:4" or "16:9"). Cannot be combined with viewport_width/viewport_height.\n    cdp_url: The CDP URL of another remote session provider.\n    profile: Browser profile configuration for state persistence.\n    auth_ids: Up to 10 unique Managed Auth connection IDs. The API verifies them inline and can return an authenticating session while login continues.\n    wait_for_authentication: Defaults to True. The SDK waits for authentication readiness through short API calls before returning from start or entering a context manager. When False, start returns after inline verification; call wait_for_auth() or await_for_auth() before browser actions if login is pending.\n    auth_retry: Number of additional retries for transient managed-auth login failures, from 0 to 2. Each retry verifies the session again before submitting credentials. A blocked connection permits one explicit login attempt.',
    "CreateFunctionRequestDict": "Request dictionary for creating a function.\n\nArgs:\n    path: The path to the function to upload.",
    "UpdateFunctionRequestDict": "Request dictionary for updating a function.\n\nArgs:\n    path: The path to the function to upload.\n    function_id: The ID of the function to update.\n    version: The version of the function to update.",
    "GetFunctionRequestDict": "Request dictionary for getting a function.\n\nArgs:\n    function_id: The ID of the function to get.\n    version: The version of the function to get.",
    "ListFunctionsRequestDict": "Request dictionary for listing functions.\n\nArgs:\n    only_active: Whether to only list active functions.\n    page: The page number to list functions for.\n    page_size: The number of functions to list per page.",
    "PersonaCreateRequestDict": "Request dictionary for creating a new persona.",
    "PersonaListRequestDict": "Request dictionary for listing personas.",
    "MessageReadRequestDict": """Request dictionary for reading emails.

    Args:
        limit: Max number of emails to return
        timedelta: Return only emails that are not older than `timedelta`
        unread_only: Return only previously unread emails
    """,
}
# Existing public keyword surface; runtime exceptions live in _compat/profiles.py.
HIDDEN_KEYWORDS = {
    "ApiSessionStartRequest": {"screenshot_type", "demonstrate"},
    "ListSessionsParametersQuery": {"only_current_token"},
    "BodyFunctionCreateFunctionsPost": {"response_format"},
    "FunctionUpdateParametersQuery": {"restricted"},
    "ListFunctionsParametersQuery": {"only_current_token", "include_system"},
    "ListFunctionRunsByFunctionIdParametersQuery": {"only_current_token", "include_system", "source"},
    "FunctionDownloadUrlParametersQuery": {"decryption_key"},
    "FunctionRunUpdateRequest": {"payloads", "result_preview"},
    "ListPersonasParametersQuery": {"only_current_token", "include_system"},
    "ProfileListParametersQuery": {"only_active", "only_current_token"},
    "ListVaultsParametersQuery": {"only_current_token", "include_system"},
}
NON_NULL_KEYWORDS = {
    "ProfileCreateRequest": {"name"},
    "ProfileListParametersQuery": {"name"},
    "CredentialsDictInput": {"email", "username", "mfa_secret"},
}
# The SDK flattens these nested body fields into public kwargs. Field inventories
# still come from the schema-derived models, including the standalone dictionaries.
FLATTENED_KEYWORDS = {
    "AddCredentialsRequest": {"credentials": "CredentialsDictInput"},
    "AddCreditCardRequest": {"credit_card": "CreditCardDictInput"},
}
OPTIONAL_KEYWORDS = {
    "FunctionRunUpdateRequest": {"status"},
    "VaultCredentialsGetParametersQuery": {"url"},
    "VaultCredentialsDeleteParametersQuery": {"url"},
}
EMPTY_REQUESTS = {
    "vault_delete": "DeleteVaultRequest",
    "vault_credentials_list": "ListCredentialsRequest",
    "vault_credit_card_delete": "DeleteCreditCardRequest",
    "vault_credit_card_get": "GetCreditCardRequest",
}
RESULT_FIELDS = {"profile_delete": "success"}
RESOURCE_HEADER = (
    "# Generated by scripts/generate_sdk_endpoints.py; do not edit.\n# pyright: reportImportCycles=false\n"
)


def _binding(index: dict[str, str], ref: str) -> Binding:
    if ref not in index:
        raise GenerationError(f"No generated model for {ref}")
    name = index[ref]
    model = cast(type[BaseModel], getattr(_generated_models(), name))
    alias, public_name = MODEL_OVERRIDES.get(name, ("models", name))
    return Binding(alias, public_name, model)


def _bound(index: dict[str, str], op: Operation, spec: JsonObject, *, method: bool = True) -> Bound:
    """Bind an operation's models. `method=False` binds only its factory (hand-written primary method)."""
    entry = NAMING[op.op_id]
    # Function clients expose the page envelope, unlike other list clients.
    if op.name in {"list_functions", "list_function_runs_by_function_id"}:
        op = replace(op, response_shape="object", response_schema=f"PaginatedResponse_{op.response_schema}_")
    # Existing SDK calls omit these optional API-only metadata switches.
    if op.name in {"session_cookies_set", "session_cookies_get", "session_offset"}:
        op = replace(op, query_params={})
    if op.response_shape == "untyped" and (entry.get("pythonRawResponse") or not method):
        op = replace(op, response_shape="raw")
    if op.response_shape == "binary" and not (entry.get("pythonBinaryResponse") or not method):
        raise GenerationError(f"{op.name}: binary response needs `pythonBinaryResponse`")
    if op.response_shape not in {"object", "array", "page", "none", "raw", "binary"} or (
        op.response_schema is None and op.response_shape not in {"none", "raw", "binary"}
    ):
        raise GenerationError(f"{op.name}: unsupported resource response {op.response_shape}")
    # Factories leave headers to the caller (`BaseClient.request(headers=...)`).
    if (method and set(op.header_params) != set(entry.get("pythonHeaders", []))) or op.method not in {
        "GET",
        "POST",
        "PATCH",
        "DELETE",
    }:
        raise GenerationError(f"{op.name}: unsupported headers/method")
    body = query = None
    files: dict[str, str] = {}
    page = op.name in PAGE_OPERATIONS
    if op.body_content_type:
        multipart = op.body_content_type == "multipart/form-data"
        if (
            not (op.body_content_type == "application/json" or multipart)
            or (op.body_schema is None and not page)
            or not op.body_required
        ):
            raise GenerationError(f"{op.name}: unsupported resource body")
        if op.body_schema is not None:
            body = _binding(index, f"#/components/schemas/{op.body_schema}")
        if multipart:
            assert body is not None
            properties = cast(JsonObject, spec["components"]["schemas"][op.body_schema]).get("properties", {})
            renames = FILE_KEYWORDS.get(body.model.__name__, {})
            files = {
                name: renames.get(name, name)
                for name, schema in cast(JsonObject, properties).items()
                if cast(JsonObject, schema).get("contentMediaType") == "application/octet-stream"
                or cast(JsonObject, schema).get("format") == "binary"
            }
            if not files:
                raise GenerationError(f"{op.name}: multipart body without a file field")
    if op.query_params:
        query = _binding(index, f"#/paths/{op.path.lstrip('/')}/{op.method.lower()}/parameters")
    response = (
        Binding("runtime", "RawResponse", BaseModel)
        if op.response_shape in {"none", "raw", "binary"}
        else _binding(index, f"#/components/schemas/{op.response_schema}")
    )
    if page:
        # Shared with local sessions: core models at the public boundary.
        body_model, _ = PAGE_OPERATIONS[op.name]
        response_name = CORE_OPERATIONS[op.name][1]
        assert response_name is not None
        response = Binding("core", response_name, getattr(wire_types, response_name))
        body = None if "." in body_model else Binding("core", body_model, getattr(wire_types, body_model))
    # Preserve the existing public wire paths (including their trailing slash).
    if op.name in {"list_functions", "list_function_runs_by_function_id", "list_sessions", "function_create"}:
        op = replace(op, path=op.path.rstrip("/") + "/")
    return Bound(op, body, response, query, files, page)


def _keywords(binding: Binding, classes: dict[str, ast.ClassDef]) -> str:
    name = binding.model.__name__
    keyword_name = KEYWORD_NAMES.get(name, f"{name}Dict")
    lines = [f"class {keyword_name}(TypedDict):"]
    if docstring := KEYWORD_DOCSTRINGS.get(keyword_name):
        lines.append(f"    {docstring!r}")
    for node in classes[name].body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        field = node.target.id
        if field not in binding.model.model_fields or field in HIDDEN_KEYWORDS.get(name, set()):
            continue
        if nested := FLATTENED_KEYWORDS.get(name, {}).get(field):
            model = cast(type[BaseModel], getattr(_generated_models(), nested))
            lines.extend(_keywords(Binding("models", nested, model), classes).splitlines()[1:])
            continue
        annotation = node.annotation
        if isinstance(annotation, ast.Subscript) and ast.unparse(annotation.value) == "Annotated":
            assert isinstance(annotation.slice, ast.Tuple)
            annotation = annotation.slice.elts[0]
        if field in NON_NULL_KEYWORDS.get(name, set()) and isinstance(annotation, ast.BinOp):
            if ast.unparse(annotation.right) != "None":
                raise GenerationError(f"{name}.{field}: expected nullable keyword")
            annotation = annotation.left
        if replacement := KEYWORD_ANNOTATIONS.get(name, {}).get(field):
            annotation = ast.parse(replacement, mode="eval").body

        # Qualify upstream generated model/enum references, preserving their exact types.
        class Qualify(ast.NodeTransformer):
            @override
            def visit_Name(self, node: ast.Name) -> ast.expr:
                if node.id in classes:
                    for base in classes[node.id].bases:
                        if isinstance(base, ast.Subscript) and ast.unparse(base.value) == "RootModel":
                            primitive = base.slice
                            if isinstance(primitive, ast.Name) and primitive.id in {"str", "int", "float", "bool"}:
                                return primitive
                    alias, public = MODEL_OVERRIDES.get(node.id, ("models", node.id))
                    return ast.Attribute(value=ast.Name(id=alias, ctx=ast.Load()), attr=public, ctx=ast.Load())
                return node

        if not replacement:
            annotation = Qualify().visit(annotation)
        # Support upstream Python annotations, not arbitrary OpenAPI schema reconstruction.
        if any(
            isinstance(n, ast.Name)
            and n.id
            not in {
                "str",
                "int",
                "bool",
                "float",
                "list",
                "dict",
                "timedelta_aliased",
                "core",
                "config",
                "models",
                "ProxySettingsDict",
                "SessionProfileDict",
                "Any",
                "Literal",
            }
            for n in ast.walk(annotation)
        ):
            raise GenerationError(f"{name}.{field}: unsupported keyword annotation {ast.unparse(annotation)}")
        required = (
            "Required"
            if binding.model.model_fields[field].is_required() and field not in OPTIONAL_KEYWORDS.get(name, set())
            else "NotRequired"
        )
        public_field = FILE_KEYWORDS.get(name, {}).get(field, field)
        lines.append(f"    {public_field}: {required}[{ast.unparse(annotation)}]")
    if name == "FunctionUpdateParametersQuery":
        lines.append("    path: Required[str]")
    return "\n".join(lines) + "\n"


def _keyword_name(binding: Binding) -> str:
    return KEYWORD_NAMES.get(binding.model.__name__, f"{binding.model.__name__}Dict")


def _method(bound: Bound, name: str) -> str:
    op = bound.operation
    assert bound.response is not None
    args = ["self", *(f"{p}: str" for p in op.path_params)]
    call_args = list(op.path_params)
    entry = NAMING[op.op_id]
    description = op.summary.replace(chr(34) * 3, " ")
    doc = f"{description} (`{op.method} {op.path}`)."
    if op.description:
        doc += "\n\n" + op.description.replace(chr(34) * 3, " ")
    lines: list[str] = ["        " + repr(doc)]
    if bound.page and bound.body is None:
        # An inline union body (the action to execute) is passed as a model.
        args.append(f"body: {PAGE_OPERATIONS[op.name][0]}")
        call_args.append("body")
    if bound.body and bound.query or op.header_params:
        args.append("*")
    if bound.body and bound.query:
        args.append(f"query: {_keyword_name(bound.query)} | None = None")
        call_args.append("params=wire_request(None, query or {})")
    for header in op.header_params:
        args.append(f"{header.replace('-', '_')}: str")
    if request := bound.body or bound.query:
        keyword_name = _keyword_name(request)
        if bound.page and bound.body is not None:
            keyword_name = f"core.{PAGE_OPERATIONS[op.name][1]}"
        args.append(f"**data: Unpack[{keyword_name}]")
        if op.name == "profile_list":
            lines.append('        _ = data.setdefault("page_size", 20)  # SDK default differs from API 10.')
        if op.name == "list_function_runs_by_function_id":
            lines.append('        _ = data.setdefault("only_active", True)')
        if bound.page and bound.body is not None:
            # Validated like PageClient: core models serialize `response_format` and friends.
            lines.append(f"        request = {bound.body.ref}.model_validate(data)")
        elif bound.files:
            # File fields are local paths, uploaded as files; the other fields are form fields.
            uploads = ", ".join(f"{field!r}: data[{keyword!r}]" for field, keyword in bound.files.items())
            lines.append(f"        files = {{{uploads}}}")
            fields = f"{{key: value for key, value in data.items() if key not in {sorted(bound.files.values())!r}}}"
            lines.append(f"        request = wire_request({request.ref}, {fields})")
        elif op.name == "session_start":
            lines.append(
                "        request = wire_request(None, core.SessionStartRequest.from_data(dict(data)).model_dump(context={'wire': True}))"
            )
        elif request.model.__name__ in FLATTENED_KEYWORDS:
            for field_name in FLATTENED_KEYWORDS[request.model.__name__]:
                others = [name for name in request.model.model_fields if name != field_name]
                lines.append("        values = dict(data)")
                lines.append(
                    f"        nested = {{key: values.pop(key) for key in list(values) if key not in {others!r}}}"
                )
                lines.append(f"        values[{field_name!r}] = nested")
            lines.append(f"        request = wire_request({request.ref}, values)")
        else:
            lines.append(f"        request = wire_request({request.ref}, data)")
        call_args.insert(len(op.path_params), "request") if bound.body else call_args.append("params=request")
    if empty := EMPTY_REQUESTS.get(op.name):
        args.append(f"**data: Unpack[{empty}Dict]")

    returns = bound.response.ref
    runtime = "request"
    if op.response_shape == "array" or entry.get("pythonUnwrapItems"):
        runtime, returns = "request_list", f"Sequence[{returns}]"
    endpoint = f"{'page_api' if bound.page else 'api'}.{op.name}({', '.join(call_args)})"
    if op.name in EMPTY_REQUESTS:
        lines.append(f"        endpoint = {endpoint}")
        lines.append("        if data:\n            endpoint = endpoint.with_params(wire_request(None, data))")
        endpoint = "endpoint"
    if op.response_shape == "raw":
        runtime, returns = "_request", "Any"
    if op.response_shape == "binary":
        runtime, returns = "request_bytes", "bytes"
    if bound.files:
        endpoint += ", files"
        runtime = "request_upload"
    headers = ""
    if op.header_params:
        headers = (
            ", headers={" + ", ".join(f"{header!r}: {header.replace('-', '_')}" for header in op.header_params) + "}"
        )
    raw = ", check_response_detail=False" if op.response_shape == "raw" else ""
    call = f"self.{runtime}({endpoint}{headers}{raw})"
    if op.name == "session_auth_readiness":
        call = f"self.{runtime}({endpoint}, timeout=10)"
    if field := RESULT_FIELDS.get(op.name):
        annotation = bound.response.model.model_fields[field].annotation
        if not (isinstance(annotation, type) and issubclass(annotation, bool)):
            raise GenerationError(f"{op.name}: result field must remain bool")
        call, returns = f"{call}.{field}", "bool"
    lines.append(f"        _ = {call}" if op.response_shape == "none" else f"        return {call}")
    if op.response_shape == "none":
        returns = "None"
    decorator = f"    @track_usage({entry['telemetry']!r})\n" if entry.get("telemetry") else ""
    return decorator + f"    def {name}({', '.join(args)}) -> {returns}:\n" + "\n".join(lines) + "\n"


def render_resources(spec: JsonObject) -> dict[str, str]:
    check_naming(spec)
    index = cast(dict[str, str], json.loads((SDK_SRC / "_generated/schema_index.json").read_text()))
    tree = ast.parse((SDK_SRC / "_generated/models.py").read_text())
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    operations = {op.name: op for op in _parse(spec)}
    imports = (
        "from notte_core import types as core\nfrom notte_sdk._generated import models, nested_models\n"
        + "".join(
            f"from notte_sdk._compat import {alias.removesuffix('_compat')} as {alias}\n"
            for alias in sorted({alias for alias, _ in MODEL_OVERRIDES.values() if alias.endswith("_compat")})
        )
    )
    factories = (
        RESOURCE_HEADER + "from urllib.parse import quote\nfrom notte_sdk.endpoints import base as runtime\n" + imports
    )
    factories += 'from pydantic import BaseModel\nfrom notte_sdk.endpoints.base import NotteEndpoint\n\ndef _segment(value: str) -> str:\n    return quote(value, safe="")\n'
    clients = (
        RESOURCE_HEADER
        + "from collections.abc import Sequence\nfrom typing import TYPE_CHECKING, Any, Unpack\nfrom notte_core.telemetry import track_usage\n"
        + imports
    )
    clients += "from notte_core import actions\nfrom notte_sdk._requests import wire_request\nfrom notte_sdk._generated import operations as api\nfrom notte_sdk._generated import endpoints as page_api\nfrom notte_sdk._generated.typing import *\nfrom notte_sdk.endpoints.base import BaseClient\n"
    clients += "\nif TYPE_CHECKING:\n    from notte_sdk.client import NotteClient\n"
    keywords: dict[str, str] = {}
    public: dict[str, str] = {
        "Credential": "credentials.Credential",
        **{
            name: f"core.{name}"
            for name in (
                "WebSocketUrls",
                "Cookie",
                "NotteProxy",
                "ExternalProxy",
                "ProxySettings",
                "ManagedAuthOperation",
                "TabSessionDebugResponse",
                "SessionProfile",
                "TailnetProxy",
            )
        },
        "SessionProfileDict": "typing.SessionProfileDict",
        "ProxySettingsDict": "typing.ProxySettingsDict",
        "CreateFunctionRequest": "core.CreateFunctionRequest",
        "UpdateFunctionRequest": "core.UpdateFunctionRequest",
        "FunctionRunListItemResponse": "core.FunctionRunListItemResponse",
        "SessionFile": "models.SessionFile",
        "FileSource": "models.FileSource",
    }
    for resource in RESOURCES:
        base = "RunPayloadsOperations" if resource.name == "Functions" else "BaseClient"
        clients += f"\n\nclass {resource.name}Operations({base}):\n"
        if resource.client_path:
            clients += f"""
    def __init__(self, root_client: "NotteClient", api_key: str | None = None,
                 server_url: str | None = None, verbose: bool = False):
        super().__init__(root_client=root_client, base_endpoint_path={resource.client_path!r},
                         api_key=api_key, server_url=server_url, verbose=verbose)
"""
        for name in _factories(resource.name):
            if name not in operations:
                raise GenerationError(f"Migrated operation {name} is absent from the spec")
            bound = _bound(index, operations[name], spec, method=not NAMING[name].get("pythonImplementation"))
            factory = _render_operation(bound)
            for request in (bound.body, bound.query):
                if request:
                    factory = factory.replace(f": {request.ref}", ": BaseModel")
            factories += "\n\n" + factory + "\n"
        for name, method in resource.methods:
            if name not in operations:
                raise GenerationError(f"Migrated operation {name} is absent from the spec")
            bound = _bound(index, operations[name], spec)
            for binding in (bound.body, bound.query, bound.response):
                if (
                    binding is None
                    or binding.alias == "runtime"
                    or binding.model.__name__ == "ProfileDeleteResponse"
                    or (bound.page and binding is not bound.query)
                    # Multipart bodies are keyword dictionaries plus local files, not public models.
                    or (bound.files and binding is bound.body)
                ):
                    continue
                public_name = (
                    KEYWORD_NAMES.get(binding.model.__name__, "").removesuffix("Dict")
                    if binding is not bound.response
                    else ""
                )
                public[public_name or binding.name] = binding.ref
            clients += "\n" + _method(bound, method)
            for request in (bound.body, bound.query):
                if request and not (bound.page and request is bound.body):
                    keywords[_keyword_name(request)] = _keywords(request, classes)
    for nested in (
        "CredentialsDictInput",
        "CreditCardDictInput",
        "BodyFunctionCreateFunctionsPost",
        "FunctionUpdateParametersQuery",
        "NotteProxy",
        "ExternalProxy",
        "TailnetProxy",
        "SessionProfile",
    ):
        model = cast(type[BaseModel], getattr(_generated_models(), nested))
        keywords[KEYWORD_NAMES.get(nested, f"{nested}Dict")] = _keywords(Binding("models", nested, model), classes)
    nested_names = ["NotteProxyDict", "ExternalProxyDict", "TailnetProxyDict", "SessionProfileDict"]
    keywords = {
        **{name: keywords.pop(name) for name in nested_names},
        "ProxySettingsDict": 'ProxySettingsDict = Annotated[NotteProxyDict | ExternalProxyDict | TailnetProxyDict, Field(discriminator="type")]\n',
        **keywords,
    }
    for empty in EMPTY_REQUESTS.values():
        keywords[f"{empty}Dict"] = f"class {empty}Dict(TypedDict):\n    pass\n"
    # Explicit imports keep generated typing strict and avoid wildcard exports.
    keyword_names = list(keywords)
    clients = clients.replace(
        "from notte_sdk._generated.typing import *",
        "from notte_sdk._generated.typing import " + ", ".join(keyword_names),
    )
    typing = (
        RESOURCE_HEADER
        + "from datetime import timedelta as timedelta_aliased\nfrom typing import Annotated, Any, Literal, NotRequired, Required\nfrom pydantic import Field\nfrom notte_core import types as core\nfrom notte_core import config\nfrom notte_sdk._generated import models\nfrom typing_extensions import TypedDict\n\n\n"
        + "\n\n".join(keywords.values())
    )
    public.update({name: f"typing.{name}" for name in keyword_names})
    public.update({name: f"requests.{name}" for name in EMPTY_REQUESTS.values()})
    public_module = RESOURCE_HEADER
    for name, ref in sorted(public.items()):
        alias, model_name = ref.split(".")
        module = f"_compat.{alias.removesuffix('_compat')}" if alias.endswith("_compat") else f"_generated.{alias}"
        source = (
            "notte_core.types"
            if alias == "core"
            else "notte_core.credentials.base"
            if alias == "credentials"
            else f"notte_sdk.{module}"
        )
        public_module += f"from {source} import {model_name} as {name}\n"
    public_module += f"\n__all__ = {sorted(public)!r}\n"
    empty_models = RESOURCE_HEADER + "from pydantic import BaseModel\n\n"
    for empty in EMPTY_REQUESTS.values():
        empty_models += f"\nclass {empty}(BaseModel):\n    pass\n"

    # Plain-data envelopes with nested behavioral objects are also generated:
    # reuse the upstream AST and apply the same core type mapping to annotations.
    class CoreNames(ast.NodeTransformer):
        @override
        def visit_Name(self, node: ast.Name) -> ast.expr:
            alias, name = MODEL_OVERRIDES.get(node.id, ("models", node.id))
            if alias == "core":
                return ast.Attribute(value=ast.Name(id="core", ctx=ast.Load()), attr=name, ctx=ast.Load())
            return node

    nested = (
        RESOURCE_HEADER
        + "from typing import Annotated\nfrom pydantic import BaseModel, Field\nfrom notte_core import types as core\n\n"
    )
    for name, (alias, _) in MODEL_OVERRIDES.items():
        if alias == "nested_models":
            nested += ast.unparse(CoreNames().visit(classes[name])) + "\n\n"
    outputs = {
        "nested_models.py": nested,
        "operations.py": factories,
        "resources.py": clients,
        "typing.py": typing,
        "requests.py": empty_models,
        "public.py": public_module,
    }
    with tempfile.TemporaryDirectory(prefix="notte-sdk-resources-") as directory:
        for name, source in outputs.items():
            path = Path(directory) / name
            _ = path.write_text(source)
            for args in (["check", "--select", "E4,E7,E9,F,I", "--fix"], ["format", "--line-length", "120"]):
                _ = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "ruff",
                        *args,
                        "--isolated",
                        "--config",
                        'lint.isort.known-first-party=["notte_sdk"]',
                        str(path),
                    ],
                    check=True,
                    capture_output=True,
                )
            outputs[name] = path.read_text()
    return outputs


def migrated_contracts(spec: JsonObject) -> dict[str, str]:
    """Include referenced schemas in the production gate, not just factory names."""
    wanted = {name for resource in RESOURCES for name in (*resource.operations, *_factories(resource.name))}
    contracts: dict[str, str] = {}
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            operation = cast(JsonObject, operation)
            if operation.get("operationId") not in wanted:
                continue
            schemas: dict[str, object] = {}

            def wire(value: object, *, names: bool = False) -> object:
                if isinstance(value, list):
                    return [wire(item) for item in cast(list[object], value)]
                if not isinstance(value, dict):
                    return value
                obj = cast(JsonObject, value)
                # These dictionaries contain user-defined names, not schema keywords.
                if names:
                    return {key: wire(item) for key, item in obj.items()}
                ref = obj.get("$ref")
                if isinstance(ref, str) and ref not in schemas:
                    target: JsonObject = spec
                    for part in ref.removeprefix("#/").split("/"):
                        target = target[part.replace("~1", "/").replace("~0", "~")]
                    schemas[ref] = None  # break recursive schema references
                    schemas[ref] = wire(target)
                docs = {
                    "title",
                    "description",
                    "summary",
                    "example",
                    "examples",
                    "externalDocs",
                    "x-codeSamples",
                    "tags",
                    "$comment",
                }
                maps = {
                    "properties",
                    "patternProperties",
                    "$defs",
                    "definitions",
                    "dependentSchemas",
                    "responses",
                    "content",
                    "headers",
                    "mapping",
                }
                # Defaults/enum/const are literal JSON, even if they contain `$ref` or
                # fields called `description`. Security requirements also use free names.
                literals = {"default", "enum", "const", "security"}
                return {
                    key: item if key in literals else wire(item, names=key in maps)
                    for key, item in obj.items()
                    if key not in docs
                }

            operation_contract = wire(operation)
            contracts[operation["operationId"]] = json.dumps(
                [path, method, operation_contract, schemas], sort_keys=True
            )
    return contracts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = parser.add_argument("--check", action="store_true", help="fail if the generated module is stale")
    _ = parser.add_argument("--against", metavar="URL", help="with --check: compare the operations the SDK calls")
    _ = parser.add_argument("--report", action="store_true", help="list the operations the SDK calls and does not")
    args = parser.parse_args()

    spec = cast(JsonObject, json.loads(SNAPSHOT.read_text()))
    try:
        text, blocks = render(spec)
    except GenerationError as e:
        print(f"Cannot generate the SDK endpoints: {e}", file=sys.stderr)
        return 1
    from scripts.generate_sdk_models import check_or_write

    try:
        resources = render_resources(spec)
    except ValueError as e:
        print(f"Cannot generate SDK resources: {e}", file=sys.stderr)
        return 1
    target = OUTPUT.relative_to(REPO_ROOT)

    available = blocks.keys() | migrated_contracts(spec).keys()
    if args.report:
        used = used_operations()
        for name in sorted(available):
            print(f"{'used  ' if name in used else 'unused'} {name}")
        for name in sorted(used.keys() - available):
            print(f"MISSING {name} (called in {', '.join(used[name])})")
        return 0

    if args.check:
        if not check_or_write(resources, OUTPUT.parent, check=True):
            return 1
        if not OUTPUT.exists() or OUTPUT.read_text() != text:
            print(f"{target} is stale: run `make sdk-endpoints` and commit the result.", file=sys.stderr)
            return 1
        if missing := sorted(used_operations().keys() - available):
            print(f"The SDK calls operations the spec lacks: {', '.join(missing)}", file=sys.stderr)
            return 1
        if args.against:
            return _check_against(args.against, blocks)
        print(f"{target} is up to date ({len(blocks)} operations).")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    init = OUTPUT.parent / "__init__.py"
    if not init.exists():
        _ = init.write_text('"""Code generated from the OpenAPI snapshot. Do not edit."""\n')
    _ = check_or_write(resources, OUTPUT.parent, check=False)
    _ = OUTPUT.write_text(text)
    print(f"wrote {target} ({len(blocks)} operations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
