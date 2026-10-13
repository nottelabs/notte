#!/usr/bin/env python3
"""Generate the Python SDK's HTTP endpoint layer from the OpenAPI snapshot.

``openapi/openapi.json`` describes every operation of the Notte API. This script turns each
one into a factory in ``notte_sdk/_generated/endpoints.py`` that returns a ``NotteEndpoint``
(method, path, path/query parameters, request and response model), so the hand-written
clients in ``notte_sdk.endpoints`` stop spelling paths and methods by hand.

Migrated resources also get typed operations, invocation methods and keyword dictionaries,
bound through the upstream-generated schema index (see RESOURCES below). The transitional
endpoint layer still binds hand-written models in
``notte_core.types`` (the source of truth, see docs/design/openapi-contract.md); operations
are bound to them by schema name:

- the schema's namesake in ``notte_core.types`` (or ``notte_core.credentials.base``), with
  ``openapi_contract.SCHEMA_NAMES`` for models the API names differently and FastAPI's
  ``-Input`` / ``-Output`` split;
- ``RESPONSE_MODELS`` / ``REQUEST_MODELS`` below, where the SDK binds a model whose name is
  neither (checked here for field compatibility);
- ``QUERY_MODELS`` below for query parameters, which FastAPI flattens into the operation.

A schema without a model is not generated: the body is typed ``BaseModel`` and the response
``RawResponse`` (the JSON object, untyped), and the docstring says so.

    uv run --no-sync python scripts/generate_sdk_endpoints.py                  # write the module
    uv run --no-sync python scripts/generate_sdk_endpoints.py --check          # fail if it is stale
    uv run --no-sync python scripts/generate_sdk_endpoints.py --check --against URL  # release gate
    uv run --no-sync python scripts/generate_sdk_endpoints.py --report         # used / unused operations
"""

from __future__ import annotations

import argparse
import ast
import difflib
import importlib.util
import inspect
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from notte_core import types as wire_types
from notte_core.credentials import base as credentials_base
from pydantic import AliasChoices, BaseModel
from pydantic.fields import FieldInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.openapi_contract import SCHEMA_NAMES, download  # noqa: E402

SNAPSHOT = REPO_ROOT / "openapi" / "openapi.json"
SDK_SRC = REPO_ROOT / "packages" / "notte-sdk" / "src" / "notte_sdk"
OUTPUT = SDK_SRC / "_generated" / "endpoints.py"

# Modules whose models bind to schemas, with the alias the generated module imports them as.
MODEL_MODULES = {"wire": wire_types, "credentials": credentials_base}

# operationId -> model, where the SDK parses a response with a model that is not the schema's
# namesake. Each entry is checked: the model's required fields must exist in the schema.
RESPONSE_MODELS = {
    "page_execute": "ExecutionResultResponse",  # schema ApiExecutionResponse
    "page_observe": "ObserveResponse",  # alias of Observation
    "page_scrape": "ScrapeResponse",  # alias of DataSpace
    "scrape_webpage": "ScrapeResponse",  # alias of DataSpace
    "profile_delete": "ExecutionResponse",  # schema ProfileDeleteResponse, same fields
    "session_auth_readiness": "SessionAuthResponse",  # schema ManagedAuthReadiness
    "session_cookies_set": "SetCookiesResponse",  # schema ExecutionResponse, same fields
}

# operationId -> model for request bodies FastAPI renders as an anonymous `Body_...` schema.
REQUEST_MODELS = {
    "session_cookies_set": "SetCookiesRequest",
}

# operationId -> model holding the operation's query parameters. Its fields must be query
# parameters of the operation, and it must cover the required ones.
QUERY_MODELS = {
    "function_download_url": "GetFunctionRequest",
    "list_function_runs_by_function_id": "ListFunctionRunsRequest",
    "list_functions": "ListFunctionsRequest",
    "list_personas": "PersonaListRequest",
    "list_sessions": "SessionListRequest",
    "list_vaults": "VaultListRequest",
    "persona_emails_list": "MessageReadRequest",
    "persona_sms_list": "MessageReadRequest",
    "profile_list": "ProfileListRequest",
    "session_stop": "SessionStopRequest",
    "vault_credentials_delete": "DeleteCredentialsRequest",
    "vault_credentials_get": "GetCredentialsRequest",
}

# Headers the client sets on every request (BaseClient.headers), so they are not parameters.
CLIENT_HEADERS = {"authorization", "x-notte-request-origin", "x-notte-sdk-version", "x-db-preview"}

# The hand-written clients call the generated factories as `api.<operation>(...)`.
USAGE_PATTERN = re.compile(r"\bapi\.([a-z_][a-z0-9_]*)\(")

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


def _models() -> dict[str, Binding]:
    index: dict[str, Binding] = {}
    # wire_types last so it wins when both modules export a name.
    for alias in ("credentials", "wire"):
        module = MODEL_MODULES[alias]
        for name, obj in vars(module).items():
            if not (inspect.isclass(obj) and issubclass(obj, BaseModel) and name[0].isupper()):
                continue
            # Defined in the module, or an alias assigned there (`ObserveResponse = Observation`);
            # plain imports are not part of its interface.
            if obj.__module__ == module.__name__ or obj.__name__ != name:
                index[name] = Binding(alias, name, obj)
    return index


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


def _namesake(models: dict[str, Binding], schema: str) -> Binding | None:
    by_schema = {schema_name: model_name for model_name, schema_name in SCHEMA_NAMES.items()}
    for candidate in (by_schema.get(schema), schema.removesuffix("-Input").removesuffix("-Output")):
        if candidate is not None and candidate in models:
            return models[candidate]
    return None


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


def _bind(spec: JsonObject, operations: list[Operation], models: dict[str, Binding], strict: bool) -> list[Bound]:
    """Bind every operation to its models.

    Not strict (a live API in the release gate): an operation that does not bind is left out,
    so only the operations the SDK calls can fail the check.
    """
    by_id = {o.op_id: o for o in operations}
    for table in (RESPONSE_MODELS, REQUEST_MODELS, QUERY_MODELS):
        for op_id, model in table.items():
            if model not in models:
                raise GenerationError(f"{op_id} is bound to {model}, which is not a model in notte_core")
            if strict and op_id not in by_id:
                raise GenerationError(f"{op_id} is bound to {model} but is no longer in the spec")
    result: list[Bound] = []
    for op in operations:
        try:
            result.append(_bind_operation(cast(JsonObject, spec["components"]["schemas"]), op, models))
        except GenerationError:
            if strict:
                raise
    return result


def _bind_operation(schemas: JsonObject, op: Operation, models: dict[str, Binding]) -> Bound:
    body = response = query = None
    if op.body_schema is not None:
        if (name := REQUEST_MODELS.get(op.op_id)) is not None:
            body = models[name]
            _check_fields(f"{op.op_id} body", body, cast(JsonObject | None, schemas.get(op.body_schema)))
        else:
            body = _namesake(models, op.body_schema)
    if op.response_schema is not None:
        if (name := RESPONSE_MODELS.get(op.op_id)) is not None:
            response = models[name]
            schema = cast(JsonObject | None, schemas.get(op.response_schema))
            _check_fields(f"{op.op_id} response", response, schema)
        else:
            response = _namesake(models, op.response_schema)
    if (name := QUERY_MODELS.get(op.op_id)) is not None:
        query = models[name]
        fields = set(query.model.model_fields)
        if extra := sorted(fields - op.query_params.keys()):
            raise GenerationError(f"{op.op_id}: {name} sends query parameters the API lacks: {extra}")
        required = {param for param, is_required in op.query_params.items() if is_required}
        if missing := sorted(required - fields):
            raise GenerationError(f"{op.op_id}: {name} lacks required query parameters: {missing}")
    return Bound(op, body, response, query)


def _docstring(bound: Bound) -> list[str]:
    op = bound.operation
    lines = [f"{op.summary or op.name} (`{op.method} {op.path}`)."]
    notes = list(op.notes)
    if op.body_content_type is not None and bound.body is None:
        what = f"`{op.body_schema}`" if op.body_schema else "an inline schema"
        notes.append(f"Body: {what} ({op.body_content_type}) has no model in notte_core.")
    elif op.body_content_type == "multipart/form-data":
        notes.append("Body: multipart/form-data, attach the file with `with_file`.")
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
            notes.append("Responds with a file: read it with `BaseClient.request_path`, not `request`.")
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
"""Notte API endpoints, one factory per OpenAPI operation.

Each factory returns the `NotteEndpoint` for its operation; the hand-written clients in
`notte_sdk.endpoints` send it with `BaseClient.request` / `request_list`:

    from notte_sdk._generated import endpoints as api

    persona = self.request(api.persona_get(persona_id))

Bodies and responses are the hand-written models of `notte_core.types` (bound by schema
name). Operations whose schema has no model take a plain `BaseModel` body and parse the
response as `RawResponse`; their docstrings say so. See docs/design/sdk-generated-endpoints.md.
"""

from __future__ import annotations

from urllib.parse import quote

from notte_core import types as wire
from notte_core.credentials import base as credentials
from pydantic import BaseModel

from notte_sdk.endpoints.base import NotteEndpoint, RawResponse


def _segment(value: str) -> str:
    """Encode a path parameter as a single path segment."""
    return quote(value, safe="")
'''


def render(spec: JsonObject, strict: bool = True) -> tuple[str, dict[str, str]]:
    """The generated module, and each operation's code by name."""
    models = _models()
    bound = _bind(spec, _parse(spec), models, strict)
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
    used_aliases = {alias for alias in MODEL_MODULES if f"{alias}." in "".join(blocks.values())}
    text = "".join(parts)
    for alias in MODEL_MODULES:
        if alias not in used_aliases:
            text = re.sub(rf"^from .* import .* as {alias}\n", "", text, flags=re.M)
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
    operations: tuple[str, ...]


RESOURCES = (Resource("Profiles", ("profile_create", "profile_get", "profile_delete", "profile_list")),)
# Explicit, reviewed exceptions to schema-derived binding. No core wire types.
MODEL_OVERRIDES = {
    "ProfileDeleteResponse": ("profiles_compat", "ProfileDeleteResponse"),
    "ProfileResponse": ("profiles_compat", "ProfileResponse"),
    "ProfileListParametersQuery": ("profiles_compat", "ProfileListRequest"),
}
KEYWORD_NAMES = {
    "ProfileCreateRequest": "ProfileCreateRequestDict",
    "ProfileListParametersQuery": "ProfileListRequestDict",
}
# Existing public keyword surface; runtime exceptions live in _compat/profiles.py.
HIDDEN_KEYWORDS = {"ProfileListParametersQuery": {"only_active", "only_current_token"}}
NON_NULL_KEYWORDS = {"ProfileCreateRequest": {"name"}, "ProfileListParametersQuery": {"name"}}
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


def _bound(index: dict[str, str], op: Operation) -> Bound:
    if op.response_shape not in {"object", "array", "page"} or op.response_schema is None:
        raise GenerationError(f"{op.name}: unsupported resource response {op.response_shape}")
    if op.header_params or op.method not in {"GET", "POST", "PATCH", "DELETE"}:
        raise GenerationError(f"{op.name}: unsupported headers/method")
    body = query = None
    if op.body_content_type:
        if op.body_content_type != "application/json" or op.body_schema is None or not op.body_required:
            raise GenerationError(f"{op.name}: unsupported resource body")
        body = _binding(index, f"#/components/schemas/{op.body_schema}")
    if op.query_params:
        query = _binding(index, f"#/paths/{op.path.lstrip('/')}/{op.method.lower()}/parameters")
    if body and query:
        raise GenerationError(f"{op.name}: combined body/query needs an explicit public signature")
    return Bound(op, body, _binding(index, f"#/components/schemas/{op.response_schema}"), query)


def _keywords(binding: Binding, classes: dict[str, ast.ClassDef]) -> str:
    name = binding.model.__name__
    keyword_name = KEYWORD_NAMES.get(name, f"{name}Dict")
    lines = [f"class {keyword_name}(TypedDict):"]
    for node in classes[name].body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        field = node.target.id
        if field not in binding.model.model_fields or field in HIDDEN_KEYWORDS.get(name, set()):
            continue
        annotation = node.annotation
        if isinstance(annotation, ast.Subscript) and ast.unparse(annotation.value) == "Annotated":
            assert isinstance(annotation.slice, ast.Tuple)
            annotation = annotation.slice.elts[0]
        if field in NON_NULL_KEYWORDS.get(name, set()) and isinstance(annotation, ast.BinOp):
            if ast.unparse(annotation.right) != "None":
                raise GenerationError(f"{name}.{field}: expected nullable keyword")
            annotation = annotation.left
        # Support upstream Python annotations, not arbitrary OpenAPI schema reconstruction.
        if any(
            isinstance(n, ast.Name) and n.id not in {"str", "int", "bool", "float", "list", "dict"}
            for n in ast.walk(annotation)
        ):
            raise GenerationError(f"{name}.{field}: unsupported keyword annotation {ast.unparse(annotation)}")
        required = "Required" if binding.model.model_fields[field].is_required() else "NotRequired"
        lines.append(f"    {field}: {required}[{ast.unparse(annotation)}]")
    return "\n".join(lines) + "\n"


def _method(bound: Bound) -> str:
    op = bound.operation
    assert bound.response is not None
    args = ["self", *(f"{p}: str" for p in op.path_params)]
    call_args = list(op.path_params)
    lines: list[str] = []
    if request := bound.body or bound.query:
        keyword_name = KEYWORD_NAMES.get(request.model.__name__, f"{request.model.__name__}Dict")
        args.append(f"**data: Unpack[{keyword_name}]")
        lines.append(f"        request = {request.ref}.model_validate(data)")
        call_args.append("request" if bound.body else "params=request")
    returns = bound.response.ref
    runtime = "request"
    if op.response_shape in {"page", "array"}:
        runtime, returns = "request_list", f"Sequence[{returns}]"
    call = f"self.{runtime}(api.{op.name}({', '.join(call_args)}))"
    if field := RESULT_FIELDS.get(op.name):
        if bound.response.model.model_fields[field].annotation is not bool:
            raise GenerationError(f"{op.name}: result field must remain bool")
        call, returns = f"{call}.{field}", "bool"
    lines.append(f"        return {call}")
    return f"    def _{op.name}({', '.join(args)}) -> {returns}:\n" + "\n".join(lines) + "\n"


def render_resources(spec: JsonObject) -> dict[str, str]:
    index = cast(dict[str, str], json.loads((SDK_SRC / "_generated/schema_index.json").read_text()))
    tree = ast.parse((SDK_SRC / "_generated/models.py").read_text())
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    operations = {op.name: op for op in _parse(spec)}
    imports = "from notte_sdk._generated import models\nfrom notte_sdk._compat import profiles as profiles_compat\n"
    factories = RESOURCE_HEADER + "from urllib.parse import quote\n" + imports
    factories += 'from notte_sdk.endpoints.base import NotteEndpoint\n\ndef _segment(value: str) -> str:\n    return quote(value, safe="")\n'
    clients = RESOURCE_HEADER + "from collections.abc import Sequence\nfrom typing import Unpack\n" + imports
    clients += "from notte_sdk._generated import operations as api\nfrom notte_sdk._generated.typing import *\nfrom notte_sdk.endpoints.base import BaseClient\n"
    keywords: dict[str, str] = {}
    for resource in RESOURCES:
        clients += f"\n\nclass {resource.name}Operations(BaseClient):\n"
        for name in resource.operations:
            if name not in operations:
                raise GenerationError(f"Migrated operation {name} is absent from the spec")
            bound = _bound(index, operations[name])
            factories += "\n\n" + _render_operation(bound) + "\n"
            clients += "\n" + _method(bound)
            if request := bound.body or bound.query:
                keywords[request.model.__name__] = _keywords(request, classes)
    # Explicit imports keep generated typing strict and avoid wildcard exports.
    keyword_names = [KEYWORD_NAMES.get(name, f"{name}Dict") for name in keywords]
    clients = clients.replace(
        "from notte_sdk._generated.typing import *",
        "from notte_sdk._generated.typing import " + ", ".join(keyword_names),
    )
    typing = (
        RESOURCE_HEADER + "from typing import NotRequired, Required, TypedDict\n\n\n" + "\n\n".join(keywords.values())
    )
    outputs = {"operations.py": factories, "resources.py": clients, "typing.py": typing}
    with tempfile.TemporaryDirectory(prefix="notte-sdk-resources-") as directory:
        for name, source in outputs.items():
            path = Path(directory) / name
            _ = path.write_text(source)
            for args in (["check", "--select", "E4,E7,E9,F,I", "--fix"], ["format", "--line-length", "120"]):
                _ = subprocess.run(
                    [sys.executable, "-m", "ruff", *args, "--isolated", str(path)], check=True, capture_output=True
                )
            outputs[name] = path.read_text()
    return outputs


def migrated_contracts(spec: JsonObject) -> dict[str, str]:
    """Include referenced schemas in the production gate, not just factory names."""
    wanted = {name for resource in RESOURCES for name in resource.operations}
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

    if args.report:
        used = used_operations()
        for name in sorted(blocks):
            print(f"{'used  ' if name in used else 'unused'} {name}")
        for name in sorted(used.keys() - blocks.keys()):
            print(f"MISSING {name} (called in {', '.join(used[name])})")
        return 0

    if args.check:
        if not check_or_write(resources, OUTPUT.parent, check=True):
            return 1
        if not OUTPUT.exists() or OUTPUT.read_text() != text:
            print(f"{target} is stale: run `make sdk-endpoints` and commit the result.", file=sys.stderr)
            return 1
        if missing := sorted(used_operations().keys() - blocks.keys()):
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
