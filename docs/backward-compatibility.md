# Backward compatibility

Notte models cross several independently deployed boundaries: the Python SDK,
the hosted API, stored trajectories, and generated clients. A change that is
valid inside one Python process can still break an older client or corrupt the
OpenAPI contract.

## Adding an optional field

Prefer an optional field with a `None` default:

```python
wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] | None = None
```

Omit `None` values at the wire boundary rather than changing the model's global
serializer:

- SDK requests should use `model_dump(exclude_none=True)` or
  `model_dump_json(exclude_none=True)`.
- FastAPI response routes should use `response_model_exclude_none=True`.
- Stored or manually assembled response payloads should apply the same rule
  before they leave the service.

This lets a new API return an object that older strict clients still accept.
Sending a newly introduced field with a non-null value still requires a server
version that supports that feature.

## Keep serialization schemas concrete

Pydantic uses a custom serializer's declared return type when it builds the
serialization JSON schema. In particular, this pattern is dangerous for models
that appear in FastAPI responses:

```python
@model_serializer(mode="wrap")
def serialize(self, handler: SerializerFunctionWrapHandler) -> Any:
    ...
```

The runtime JSON may look correct while the serialization schema becomes `{}`.
FastAPI can then publish a correct `Model-Input` schema and an unconstrained
`Model-Output` schema. Discriminated unions make this worse: generated clients
expect every mapped object to contain the discriminator, but `{}` contains no
fields at all.

Avoid model-wide serializers for omission rules. If a custom serializer is
unavoidable, give it an accurate output type and test the serialization schema,
not only the runtime payload.

## Required regression tests

For a model used by the API, cover both schema modes:

```python
for mode in ("validation", "serialization"):
    schema = Model.model_json_schema(mode=mode)
    assert schema["type"] == "object"
    assert "discriminator_field" in schema["properties"]
```

When the model belongs to a discriminated union, also inspect the generated
FastAPI OpenAPI document and verify that its input and output component schemas
remain concrete. Runtime serialization tests alone do not catch schema-only
regressions.

## Rollout checklist

1. Add the optional model field and schema regression tests.
2. Confirm SDK requests omit unset optional values at the HTTP boundary.
3. Confirm API responses omit unset optional values at every public route.
4. Update the API's pinned Notte dependency and deploy to staging.
5. Inspect the staging OpenAPI schema and regenerate every generated client.
6. Deploy production before relying on the new field in released clients.
