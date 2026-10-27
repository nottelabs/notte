#!/usr/bin/env python3
"""Check that the API's OpenAPI schema matches the hand-written wire models.

The models in ``notte_core.types`` are the source of truth: notte-api imports them and
FastAPI renders them into ``openapi.json``. Drift appears when the API overrides or
extends a model instead of changing it here. This script diffs every model against the
schema of the same name (fields, required, nullable) and compares the result with the
known drift recorded in ``openapi/known_drift.txt``:

- a new drift line fails: change the model here (or record it on purpose with
  ``--update-baseline``);
- a drift line that disappeared is reported so the baseline can shrink.

    uv run --no-sync python scripts/openapi_contract.py --check                # committed snapshot
    uv run --no-sync python scripts/openapi_contract.py --check --against URL  # live API (release gate)
    uv run --no-sync python scripts/openapi_contract.py --fetch [--url URL]    # refresh the snapshot
    uv run --no-sync python scripts/openapi_contract.py --update-baseline
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import types
import typing
import urllib.request
from pathlib import Path
from typing import Any, cast

from notte_core import types as wire_types
from pydantic import AliasChoices, BaseModel
from pydantic.fields import FieldInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.openapi_order import serialize_openapi  # noqa: E402

SNAPSHOT = REPO_ROOT / "openapi" / "openapi.json"
BASELINE = REPO_ROOT / "openapi" / "known_drift.txt"
DEFAULT_URL = "https://us-staging.notte.cc"

# Model name -> schema name, where the API names the schema differently.
SCHEMA_NAMES = {
    "SessionStartRequest": "ApiSessionStartRequest",
    "GetFunctionResponse": "FunctionResponse",
    "GetFunctionWithLinkResponse": "FunctionWithLinkResponse",
}

JsonObject = dict[str, Any]


def download(url: str) -> JsonObject:
    endpoint = f"{url.rstrip('/')}/openapi.json"
    print(f"Fetching {endpoint}")
    # The API's edge rejects urllib's default User-Agent.
    request = urllib.request.Request(endpoint, headers={"User-Agent": "notte-openapi-contract"})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - https endpoint from --url
        return cast(JsonObject, json.load(response))


def _schema(schemas: JsonObject, name: str) -> JsonObject | None:
    # FastAPI splits a model used both ways into `-Input` / `-Output` schemas.
    for candidate in (SCHEMA_NAMES.get(name, name), f"{name}-Output", f"{name}-Input"):
        if candidate in schemas:
            return cast(JsonObject, schemas[candidate])
    return None


def _nullable(prop: JsonObject) -> bool:
    branches = cast(list[JsonObject], prop.get("anyOf", []))
    return any(branch.get("type") == "null" for branch in branches)


def _wire_names(field_name: str, field: FieldInfo) -> list[str]:
    """Every key a field reads on the wire: its name, its alias and its validation aliases.

    A field such as `function_id` with `validation_alias=AliasChoices("workflow_id", "function_id")`
    matches an API property named either way, so a legacy name the API still serves is not drift.
    """
    names = [field_name]
    if field.alias is not None:
        names.append(field.alias)
    alias = field.validation_alias
    choices = alias.choices if isinstance(alias, AliasChoices) else [alias] if alias is not None else []
    for choice in choices:
        if isinstance(choice, str):
            names.append(choice)
        elif isinstance(first := choice.path[0], str):  # an `AliasPath` reads a nested key: match its top level
            names.append(first)
    return names


def _model_drift(name: str, model: type[BaseModel], schema: JsonObject) -> list[str]:
    props = cast(JsonObject, schema.get("properties", {}))
    required = set(cast(list[str], schema.get("required", [])))
    owner = {
        wire: field_name for field_name, field in model.model_fields.items() for wire in _wire_names(field_name, field)
    }
    drift = [f"{name}: api-only field {k}{' (required)' if k in required else ''}" for k in props if k not in owner]
    drift += [
        f"{name}: sdk-only field {field_name}"
        for field_name, field in model.model_fields.items()
        if not any(wire in props for wire in _wire_names(field_name, field))
    ]
    for prop_name in sorted(props.keys() & owner.keys()):
        field_name = owner[prop_name]
        field, prop = model.model_fields[field_name], cast(JsonObject, props[prop_name])
        label = prop_name if prop_name == field_name else f"{prop_name} (read as {field_name})"
        if (prop_name in required) != field.is_required():
            drift.append(f"{name}: {label} required api={prop_name in required} sdk={field.is_required()}")
        sdk_nullable = types.NoneType in typing.get_args(field.annotation)
        if _nullable(prop) != sdk_nullable:
            drift.append(f"{name}: {label} nullable api={_nullable(prop)} sdk={sdk_nullable}")
    return drift


def drift(spec: JsonObject) -> list[str]:
    schemas = cast(JsonObject, spec["components"]["schemas"])
    lines: list[str] = []
    for name, obj in sorted(vars(wire_types).items()):
        if not (inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == wire_types.__name__):
            continue
        if (schema := _schema(schemas, name)) is not None:
            lines += _model_drift(name, obj, schema)
    return lines


def _baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {line for line in BASELINE.read_text().splitlines() if line and not line.startswith("#")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = parser.add_argument("--fetch", action="store_true", help="refresh the committed snapshot from --url")
    _ = parser.add_argument("--url", default=DEFAULT_URL, help=f"API base URL for --fetch (default: {DEFAULT_URL})")
    _ = parser.add_argument("--check", action="store_true", help="fail on drift that is not in the baseline")
    _ = parser.add_argument("--against", metavar="URL", help="check a live API instead of the snapshot")
    _ = parser.add_argument("--update-baseline", action="store_true", help="record the current drift as known")
    args = parser.parse_args()

    if args.fetch:
        spec = download(args.url)
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        _ = SNAPSHOT.write_text(serialize_openapi(spec))
        print(f"wrote {SNAPSHOT.relative_to(REPO_ROOT)}")

    if args.update_baseline:
        lines = drift(cast(JsonObject, json.loads(SNAPSHOT.read_text())))
        header = "# Known drift between notte_core.types and openapi/openapi.json; see scripts/openapi_contract.py.\n"
        _ = BASELINE.write_text(header + "".join(f"{line}\n" for line in lines))
        print(f"wrote {BASELINE.relative_to(REPO_ROOT)} ({len(lines)} entries)")
        return 0

    if not args.check:
        return 0

    source = args.against or str(SNAPSHOT.relative_to(REPO_ROOT))
    spec = download(args.against) if args.against else cast(JsonObject, json.loads(SNAPSHOT.read_text()))
    current, known = set(drift(spec)), _baseline()
    for line in sorted(known - current):
        print(f"resolved (remove from the baseline): {line}")
    if new := sorted(current - known):
        for line in new:
            print(f"new drift: {line}", file=sys.stderr)
        print(
            f"The wire models don't match {source}. Change notte_core.types (the source of truth) so the API "
            + "uses the same models, or record the drift with --update-baseline.",
            file=sys.stderr,
        )
        return 1
    print(f"The wire models match {source} (known drift: {len(current)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
