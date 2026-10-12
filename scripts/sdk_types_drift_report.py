#!/usr/bin/env python3
"""Report where hand-written models in notte_sdk.types drift from the OpenAPI snapshot.

Informational, never fails: it guides the migration to generated models
(docs/design/openapi-generated-sdk-types.md). Models already built on a generated
model are skipped, since the generated drift check covers them.

    uv run --no-sync python scripts/sdk_types_drift_report.py
"""

from __future__ import annotations

import inspect
import json
import types
import typing
from pathlib import Path
from typing import Any, cast

from notte_sdk import types as sdk_types
from notte_sdk._generated import models as wire
from pydantic import BaseModel

SNAPSHOT = Path(__file__).resolve().parent.parent / "packages" / "notte-sdk" / "openapi" / "openapi.json"

# SDK model name -> schema name, where the API names the schema differently.
SCHEMA_NAMES = {
    "SessionStartRequest": "ApiSessionStartRequest",
    "GetFunctionResponse": "FunctionResponse",
    "GetFunctionWithLinkResponse": "FunctionWithLinkResponse",
}

JsonObject = dict[str, Any]


def _schema(schemas: JsonObject, name: str) -> tuple[str, JsonObject] | None:
    for candidate in (SCHEMA_NAMES.get(name, name), f"{name}-Output", f"{name}-Input"):
        if candidate in schemas:
            return candidate, cast(JsonObject, schemas[candidate])
    return None


def _nullable(prop: JsonObject) -> bool:
    branches = cast(list[JsonObject], prop.get("anyOf", []))
    return any(branch.get("type") == "null" for branch in branches)


def _diff(model: type[BaseModel], schema: JsonObject) -> list[str]:
    props = cast(JsonObject, schema.get("properties", {}))
    required = set(cast(list[str], schema.get("required", [])))
    fields = model.model_fields
    diffs = [f"+api {k}{' (required)' if k in required else ''}" for k in props if k not in fields]
    diffs += [f"-api {k}" for k in fields if k not in props]
    for name in props.keys() & fields.keys():
        field, prop = fields[name], cast(JsonObject, props[name])
        if (name in required) != field.is_required():
            diffs.append(f"~required {name}: api={name in required} sdk={field.is_required()}")
        sdk_nullable = types.NoneType in typing.get_args(field.annotation)
        if _nullable(prop) != sdk_nullable:
            diffs.append(f"~nullable {name}: api={_nullable(prop)} sdk={sdk_nullable}")
    return diffs


def main() -> None:
    spec = cast(JsonObject, json.loads(SNAPSHOT.read_text()))
    schemas = cast(JsonObject, spec["components"]["schemas"])
    generated = {obj for obj in vars(wire).values() if inspect.isclass(obj) and obj.__module__ == wire.__name__}
    unmatched: list[str] = []
    for name, obj in sorted(vars(sdk_types).items()):
        if not (inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == sdk_types.__name__):
            continue
        if generated & set(obj.__mro__):
            continue
        found = _schema(schemas, name)
        if found is None:
            unmatched.append(name)
            continue
        schema_name, schema = found
        if diffs := _diff(obj, schema):
            print(f"{name} (schema {schema_name}): " + "; ".join(diffs))
    print(f"\nNo same-name schema (query params, SDK-only, or renamed): {', '.join(unmatched)}")


if __name__ == "__main__":
    main()
