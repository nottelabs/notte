# Generate the Python SDK from the committed OpenAPI contract

Status: design proposal plus a non-breaking infrastructure draft. The first PR changes no
public imports, resource methods, transport, or return types. Review the ownership and
compatibility decisions below before migrating resources.

## Ownership and recommendation

The direction is **hand-written `notte_core` types → backend FastAPI → committed
`openapi/openapi.json` → SDK-owned generated models and operations → ergonomic SDK facade**.
Core stays the backend/local browser's source. Do not generate back into core: that would
create a circular maintenance process. The SDK consumes a versioned API contract like Node.
There is no backend change in this PR.

Generate every schema in the snapshot, including types that have no core counterpart, both
FastAPI input/output variants, and operation query/body models. Generate every documented
operation in the eventual endpoint/client layer. Never substitute `BaseModel`/`RawResponse`
merely because a schema is absent from core. Genuinely free-form JSON, binary responses,
streaming, and empty responses must be represented explicitly.

**Local and cloud wire classes will have different identities.** Keep the familiar import
names in `notte_sdk.types`, but migrate those names to SDK-owned generated types or small
compatibility wrappers resource by resource. `notte_core.types.ProfileResponse is
notte_sdk.types.ProfileResponse` will eventually be false. Pydantic validation of another
model instance does not automatically bridge that difference. This is a compatibility
change, even when every field and method signature looks identical; schedule it within v2
and document it. PR 1 preserves identity for every current public export.

Keep a dependency on core for shared *behavior*: logging/telemetry, configuration, resource
lifecycle, errors, credentials/encryption helpers, browser-independent algorithms, and
explicit domain adapters. Removing that dependency is a separate project. Generated files
must never import core. Once a resource migrates, its HTTP body/response validation must
use generated SDK models, not core's wire declarations.

## Generator choice and evidence

Rechecked PyPI and upstream documentation on 2026-10-13:

- **Choose `datamodel-code-generator==0.83.0`** for Pydantic v2 models. It generates all 198
  component schemas in this snapshot without an omission. Include `schemas`, `paths`, and
  `parameters` scopes so flattened query parameters and inline bodies are covered too.
  Keep input/output types distinct; use `Annotated` constraints, Python 3.11, explicit
  datetime mapping, strict reference resolution, and no remote references. All generated
  Pydantic classes are imported and their JSON schemas built in tests.
- That released version has **no client generation option**. Upstream main documents
  experimental `--generate-client httpx2` with `Client` and `AsyncClient` since **0.84.0**;
  it is not the current PyPI release. Do not pin a git checkout or depend on an unreleased
  experimental transport for this migration.
- `openapi-python-client==0.29.1` remains current. The prior audit's actual trial produced
  380 files / 45,301 Python lines, attrs models and sync/async HTTPX functions, with omitted
  execute/function-run endpoints and observe response/model collisions. These results were
  not rerun in this PR; the release has not changed. It would require a large compatibility
  layer and would abandon Pydantic model semantics.
- OpenAPI Generator **7.26.0** is another maintained Pydantic-capable client generator.
  Its Python docs list urllib3, asyncio, httpx and httpx2 libraries. `supportHttpxSync`
  supplies sync wrappers that wait for async methods, not an independent requests runtime.
  It is a viable future bake-off, not evidence that no Python async generator exists.
  It was documentation-reviewed here, not successfully trialled: this machine has no Java
  runtime. Adopting it also changes error handling, retries, authentication and model APIs;
  model generation alone does not require that transport migration.

Use datamodel-code-generator plus the existing in-repository operation generator. Evolve
that generator to resolve schema references through the generated index rather than
introspecting core. Generate a thin resource/client invocation layer from the same operation
metadata. Reuse the existing requests transport policy initially. This is intentionally two
generators, not a home-grown schema compiler. A released, sufficiently compatible upstream
Pydantic client generator can replace the operation generator after a request-capture
bake-off; it should not block generation of all models now.

Keep the public client **synchronous** for this series. Async is welcome as an additive
`AsyncNotteClient` when there is a real async transport and coverage for identical auth,
timeouts, cancellation, error mapping and stream cleanup. Do not advertise coroutines that
perform blocking requests as an async generated SDK. Existing async helper behavior remains
unchanged by this draft.

Sources: [model generator release](https://pypi.org/project/datamodel-code-generator/0.83.0/),
[experimental client docs](https://datamodel-code-generator.koxudaxi.dev/python-client/),
[openapi-python-client](https://pypi.org/project/openapi-python-client/0.29.1/),
[OpenAPI Generator Python 7.26.0](https://github.com/OpenAPITools/openapi-generator/blob/v7.26.0/docs/generators/python.md).

## File ownership

Current PR:

- `scripts/generate_sdk_models.py`: small driver for the pinned upstream generator, stable
  formatting, schema coverage, and a non-mutating freshness check. No schema rewrites.
- `packages/notte-sdk/src/notte_sdk/_generated/models.py`: every generated wire model,
  including inline operation models (244 Pydantic models, 45 enums; 4,563 lines). Private and side by side; not yet used by facades.
- `packages/notte-sdk/src/notte_sdk/_generated/schema_index.json`: generator source-reference
  identifiers to Python names, including input/output variants and synthesized nested types.
  Nested identifiers are generator metadata, not necessarily resolvable JSON pointers.
- `pyproject.toml` / `uv.lock`: pin datamodel-code-generator and Ruff, including transitive
  dependencies in the lock. Neither becomes an SDK runtime dependency.
- `tests/sdk/test_generated_models.py`, `tests/scripts/test_generate_sdk_models.py`:
  coverage/import/schema tests, constraints and discriminator checks, public identity
  protection, known semantic differences, deterministic output and stale-output failure.

Next PRs, after design review:

- `_generated/operations.py`: generated operation factories bound exclusively to generated
  models; keep `_generated/endpoints.py` as the transitional core-bound layer until its last
  consumer migrates. Both use `NotteEndpoint` and the existing transport initially.
- `_generated/resources.py`: generated typed invocation methods, no auth/retry/business
  policy. Start with all four public profiles methods; retain complete operation metadata
  and fail generation for unsupported response/body shapes rather than silently omit them.
- `_generated/typing.py`: schema-derived public keyword TypedDicts and action overload inputs.
  Generate from the same schema/metadata, not a second hand-written field inventory.
- `_compat/`: reviewed aliases, old defaults and conversions into domain behavior. One small
  manifest should identify each override, reason, operation and required regression test.
- `types.py`: explicit stable exports, not a wildcard core re-export after migration. Preserve
  names such as `ProfileResponse`, `ObserveResponse`, `ScrapeResponse` and request `*Dict`s;
  distinguish generated input/output classes internally. Behavior-bearing names may wrap or
  subclass generated models, but must not redeclare the wire field inventory.
- `client.py`, `endpoints/*.py`, `_transport.py`, websocket modules: hand-written ergonomic
  facade/policy. Keep session/context managers, persona inbox polling, uploads and ownership
  of file handles, presigned downloads, SSE/WebSocket handling and encryption here.

The existing generated endpoint layer and all public imports remain untouched in PR 1.

## Bridging local and cloud behavior

Prefer narrow structural protocols for new shared algorithms (read-only properties, not
mutable concrete Pydantic fields). For existing algorithms with behavior-rich core models,
use explicit adapters at the SDK boundary. Avoid core depending on SDK, broad `Any`, or
making generated SDK classes inherit core wire classes to pretend identity is unchanged.

### `act()` and PR #34 (`v2-act`)

The reviewed branch's `ActDriver.observe` takes core `Observation`, and `execute` returns
core `ExecutionResult`; `ActResult` embeds core `BaseAction`/`ExecutionResult`. Its
`ObservedPage.from_observation` consumes behavior that generated data classes do not provide.
Preserve these as domain interfaces initially. `RemoteActDriver` must convert the generated
cloud observation and execution result into the core domain objects at that boundary.
Keep `ActResult` shared because it is a local orchestration result, not an HTTP response.

Adapters should use explicit field conversions or `model_dump(mode="json", by_alias=True)`
followed by domain validation, with separate handling for selectors, action unions, secrets
and structured data. Do not blindly cast or round-trip secrets through masked JSON. Test
local and cloud drivers with the same captured observation, dry-run proposed action,
execution result, freshness behavior and `execute(result.action)` flow. Until this exists,
do not migrate session responses or change PR #34's contracts. The profile pilot is independent.

### Actions and `execute(type=..., ...)`

Keep call signatures and overload behavior, including the `evaluate_js` special return type.
Generate the cloud action keyword shapes/discriminator union from the snapshot; the local
session retains registry-derived overloads. Compare their shared action subset in CI rather
than making cloud code import the local registry as its wire contract.

At the remote facade accept core action objects for existing code as well as generated SDK
input actions. Serialize supported core actions into a dict, validate against the generated
request union, and send only fields accepted by that input schema. Generated output action
objects need an explicit output-to-input conversion; they cannot simply stand in for inputs.
Core actions retain local execution helpers. A local session may accept generated actions
through the inverse adapter for the supported common subset; until added, shared code should
use keyword calls or core action objects. Test all shared discriminators and reject unsupported
ones before HTTP. Keep overload typecheck fixtures for both session classes.

### `scrape(response_format=...)`

The caller's `type[T]` is not a wire type. The facade converts it to JSON Schema for the
request, retains the class locally, validates response data with `T.model_validate`, and
preserves the existing overload results: markdown `str`; typed `T` on success;
`StructuredData[T]` when `raise_on_failure=False`; instruction-only `dict` or its wrapper.
Keep `StructuredData` as a shared domain convenience (and its failure/unwrapping behavior),
while the HTTP response itself is validated with generated `DataSpace`. Generated models
cannot recreate `.get()`, errors or a user-defined generic from OpenAPI. Test this conversion
and inference with both basedpyright and ty before migrating page/session facades.

## Spec gaps and compatibility decisions

Do not silently correct the snapshot during generation. Tests intentionally expose these gaps:

- Some function responses declare both `workflow_id` and `function_id` required (and both
  run-id spellings). They are separate generated fields. Core currently uses
  `AliasChoices("workflow_id", "function_id")`, preferring the legacy name. Before migrating
  functions, capture real responses and either correct the backend schema or add a reviewed
  compatibility normalization that accepts either, preserves that precedence on conflict,
  and fills the generated required counterparts internally. Public exports keep the current
  `function_id` name. Request serialization must match each route's captured contract;
  do not blindly send both keys to an `extra="forbid"` request or rename legacy routes.
- `idle_timeout_minutes`/`timeout_minutes` have the same problem: retain the existing
  precedence/defaults in a facade adapter, not a global generated field rename.
- OpenAPI omits Python default factories and behavioral validators. For example generated
  `ProfileResponse.persisted_domains` is optional `None`, whereas core supplies `[]`.
  A profile compatibility wrapper over the generated model should restore `[]` when absent
  before exposing `ProfileResponse`; tests must distinguish absent from explicit null.
  Request extras, pagination limits, viewport/proxy/cookie validation and defaults need
  resource-specific parity tests. Generated models retain constraints actually in the spec.
- Password formats generate `SecretStr`. Default Pydantic JSON serialization masks it;
  credential/action adapters must preserve the existing explicit secret-unwrapping policy
  at the transport boundary, while keeping repr/logs masked. Do not send masked values.

Nine used routes are absent from this snapshot. They stay in an explicit hand-written legacy
boundary until the backend publishes them or Lucas chooses removal in a breaking release:

- `POST`/`DELETE /personas/{id}/sms/number` (two phone-number operations).
- `GET /sessions/{id}/debug/tab`.
- `POST /functions/{id}/runs/create` and `POST /functions/{id}/runs/{run_id}`.
  Do not replace the latter with documented `/runs/start`: lifecycle and SSE semantics differ.
- `POST /managed-auth/connections/{id}/check`, `/refresh`, `/reauthenticate`, and
  `GET /managed-auth/operations/{id}` (four managed-auth operations).

No generator can derive types for an absent contract. Keep the current public methods and
legacy models temporarily; track their elimination. The claim “all wire types from OpenAPI”
is complete only after these routes enter the backend-owned spec or leave the supported API.

## CI and regeneration

Run `uvx uv@latest sync --all-packages --all-extras`, then `make sdk-codegen` and commit both
artifacts. `make sdk-codegen-check` generates into a fresh temporary directory and compares
bytes, including a spec SHA256. Missing output fails too; the check does not overwrite files
or rely solely on `git diff`. Generation uses no API key, backend checkout or network schema
fetch. Versions are checked before running; Ruff matches pre-commit 0.11.10 and operates with
isolated configuration. The lock fixes transitive generator dependencies.

The `sdk-codegen` pre-commit hook covers schema, driver, artifacts, lock and configuration
changes. An explicit offline CI step runs the same check. Only the upstream-generated
`models.py` is ignored by basedpyright diagnostic reporting and its filename hook; generated
code still goes through Ruff, import checks and every-model JSON Schema construction.
Hand-written facade/generator code stays under the existing strict warning policy.

Keep `openapi_contract.py` (35 known drifts), existing endpoint checks and action-overload
checks unchanged during the parallel phase. Generated SDK models eventually need regeneration
and semantic/request-capture tests, not a second comparison against core's declarations.
Retire the SDK portion of that hand-written contract baseline as its consumers migrate;
keep a separate backend/core-to-published-spec release gate. Do not erase the baseline now
or grow it to excuse new generated drift. Update the production endpoint check to validate
migrated operations too. Node now regenerates from this same committed snapshot (`cd node-sdk && npm run generate`).
Its `npm run check:generated` compares fresh temporary output and checks the TypeScript
reference without a network spec fetch. After installing both toolchains, root
`make openapi-refresh` fetches staging and regenerates Python models/endpoints, Node
client/resources/proxy patterns and TypeScript docs; set `OPENAPI_URL=https://api.notte.cc`
for production. Commit all diffs together. The scheduled `openapi-bump.yml` proposes
one combined refresh PR for manual review; the former independent Node bump is removed.
The existing `nottelabs/notte` workflow guard and production release gate are unchanged.

## Migration order and size

1. **This PR:** design, pinned generation, all models alongside current ones, coverage tests
   and freshness gates. Zero hand-written runtime lines removed; generated output increases
   the repository. No promise of binary/source compatibility from private models.
2. **Profiles pilot, stacked only after design acceptance:** generated operation/client layer,
   generated keyword types and a public compatibility wrapper/default adapter for one
   resource. Keep `create(**data)`, `get(profile_id)`, `delete(profile_id) -> bool`,
   `list(**data) -> Sequence[ProfileResponse]`; preserve telemetry/errors/auth and list
   unwrapping. Capture method, encoded path, headers, omitted body fields, query defaults,
   page envelope, 404, delete and missing defaults. The `ProfileResponse` import name stays;
   core class identity changes deliberately. Expect ~20–40 repeated resource lines replaced;
   generator/runtime support initially adds more than this removes.
3. **Review checkpoint:** stop resource migration until Lucas reviews ownership, aliases and
   profile behavior. Sessions, functions and credentials are not part of the pilot.
4. **Later:** simple resources, then page/session adapters and overloads, then functions and
   off-spec endpoints with backend coordination; finally remove the old core-bound generator
   and endpoint layer. Add genuine async separately if selected.

Audit-based estimates, not PR 1 savings: 450–700 hand-written SDK endpoint/factory lines can
move into generated code; budget ~150–250 added generator lines. Another 60–110 transport
lines might be simplified later. Core's 2,413-line types module remains necessary for backend
and local sessions: SDK-only generation does **not** remove it. The audit's potential
600–1,000 core declaration savings are out of scope for this ownership choice. Count generated
code separately and measure actual removals per resource; never count whole ergonomic wrappers
as deletable.

Decisions requested from Lucas before the pilot: accept SDK/core class-identity divergence
inside v2; accept compatibility wrappers for public defaults and behavior; confirm ownership
of backend alias/schema and off-spec-route corrections. This draft stops at PR 1 because
those decisions affect the pilot's public return type contract.
