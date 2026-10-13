# Generate the Python SDK from the committed OpenAPI contract

Status: accepted hybrid ownership and compatibility wrappers; profiles pilot implemented on
PR #42's committed-production-spec branch. Alias and unpublished-route decisions remain open.

## Ownership and recommendation

**Hybrid ownership (approved by Lucas).** Resource types and clients come from
`openapi/openapi.json`: profiles, personas, vaults, files, functions, usage, and session
management (start/stop/status/list/cookies/replay/debug). Backend/local models remain
hand-written in core; never generate back into core. The Node SDK is cloud-only and can
generate everything.

Python's **page-operation domain types stay owned by `notte_core`** and are shared by local
and cloud sessions: action classes in `notte_core.actions` (both `execute()` inputs and
observations), `Observation`/`ObserveResponse`, `ExecutionResult`, and
`StructuredData`/`DataSpace` scrape results. The wire-model contract check
(`scripts/openapi_contract.py`, `openapi/known_drift.txt`) keeps them aligned with the spec.
Generate every schema as private data for coverage, but do not move public page-operation
names or runtime parsing to those generated copies.

Measured on the act branch, the hand-written SDK uses 104 core wire models: 61 plain data
and 43 with behavior. The page-operation group (~30 action classes plus Observation,
ExecutionResult and StructuredData) is shared with local `NotteSession` and `act()` in
PR #34 (`ObservedPage.from_observation`, `RemoteActDriver`). Generating that group would
require four converters plus an action mapping. Keeping shared core domain types needs none.

`notte_sdk.types` keeps re-exporting core page-operation types. Resource names move one
resource at a time to generated classes or thin wrapper subclasses. For profiles,
`notte_core.types.ProfileResponse is notte_sdk.types.ProfileResponse` is deliberately false
inside v2, while the public import name, fields and behavior are preserved. Arbitrary core
model instances do not automatically validate as generated resource instances.

**Thin per-resource wrappers are accepted** to restore defaults/behavior OpenAPI loses.
They inherit generated models and override only reviewed differences, without duplicating
the resource's field inventory. Generated code never imports core wire declarations; it may
bind a reviewed generated-model subclass from `_compat`. Keep shared transport, auth,
errors, logging/telemetry, configuration, encryption, and lifecycle policy in the existing
runtime/facade. Removing the core dependency is a separate project.

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

- `scripts/generate_sdk_models.py` uses pinned datamodel-code-generator, formats deterministically,
  checks complete schema coverage, and writes `_generated/models.py` and `schema_index.json`.
  The model/index artifacts from #42 are unchanged by this pilot.
- `scripts/generate_sdk_endpoints.py` still emits the transitional core-bound `endpoints.py`.
  Its resource backend resolves migrated operation models through the
  upstream schema index and emits `_generated/operations.py`, `resources.py`, and `typing.py`.
  Factories derive methods, encoded paths, body/query bindings and response shapes from the
  snapshot. Typed invocation methods validate requests and call `BaseClient.request` or
  `request_list`; keyword annotations come from upstream-generated Python annotations.
  Unsupported response/body/header/keyword shapes fail generation explicitly. The resource
  registry lists the four pilot operations; other documented profiles operations are not
  new public methods in this compatibility pilot.
- `_compat/profiles.py` contains only reviewed subclass overrides (manifest below).
- `types.py` overlays migrated public names on the transitional core re-exports. Page-domain
  exports retain core identity. After all resources migrate, replace the wildcard with an
  explicit public export inventory; do not remove existing names opportunistically here.
- `endpoints/profiles.py` retains initialization, public signatures, docstrings and telemetry
  decorators; its four method bodies forward to generated invocation methods. There are no
  profiles overloads. `client.profiles`, shared transport/auth/errors and `endpoints/base.py`
  are unchanged.
- `tests/sdk/test_profiles_codegen.py` captures compatibility. The captures were written and
  run on #42's old, main-derived profiles facade before migration (17 passing tests together
  with `test_generated_endpoints.py`), then run unchanged after migration.

### Profiles compatibility manifest

Every exception is local, accepted as preservation of today's public API, and tested:

- `ProfileResponse.persisted_domains`: generated optional `None` → independently allocated
  `[]` when absent, reject explicit null, as core does. Applies to create/get/list.
- `ProfileListRequest`: subclass of `ProfileListParametersQuery`; keep page 1, page size 20
  (spec default 10), leave page bounds to the server as before, omit API-only `only_active`
  and `only_current_token` fields from serialization, reject explicit use of these flags and
  unknown keywords. Public keyword dictionaries retain the existing fields/types.
- `ProfileDeleteResponse`: require `success` and `message` as today's `ExecutionResponse`
  does, rather than interpreting an incomplete response using the schema's success default.
  Delete still returns the validated bool, including false.
- Keyword nullability: preserve existing static `name: str` keyword annotations, while
  request models continue accepting nullable names. This is an explicit compatibility
  exception applied to schema-derived annotations, not another field inventory.

The regression captures cover method, encoded path, auth/version/origin/content-type headers,
body omission, query defaults, pagination envelope and bare-array unwrapping, 404 error class,
telemetry event names, response defaults, independent lists, and delete success/failure.

## Bridging local and cloud behavior

**No page-operation adapters are needed: shared core domain types.** Resource class identity
changes do not cross the local page-operation boundary. Prefer narrow structural protocols
for new shared algorithms; core must never depend on the SDK.

### `act()` and PR #34 (`v2-act`)

`ActDriver.observe`, `RemoteActDriver`, `ObservedPage.from_observation`, and `ActResult`
continue using core Observation, BaseAction and ExecutionResult. Their behavior and identity
remain shared by local and cloud sessions. The former observation/execution conversion plan
is not needed. Keep PR #34's contracts and tests intact.

### Actions and `execute(type=..., ...)`

Keep core action objects, the shared action registry, public overloads and `evaluate_js`'s
special result. Observations contain the same core actions accepted by `execute()` and
`act()`. The former cloud input/output action union mapping and inverse local adapter are
not needed. Continue the existing registry-derived overload checks and wire contract gate.

### `scrape(response_format=...)`

Keep `StructuredData` and `DataSpace` in core, including `.get()`, failures and generic
behavior. The facade still converts caller `type[T]` to JSON Schema and validates returned
data with that type, preserving markdown `str`, typed `T`, `StructuredData[T]`, and
instruction-only results. A generated DataSpace-to-core adapter is not needed; keep existing
local/cloud overload and behavior tests. Session management can migrate independently of
these shared page-operation methods.

## Spec gaps and compatibility decisions

Do not silently correct the snapshot during generation. Tests intentionally expose these gaps:

- **Open question, not decided:** alias duplicates `workflow_id`/`function_id` (including
  run-id spellings) and `idle_timeout_minutes`/`timeout_minutes`. Recommendation: fix aliases
  in the backend schema so it describes accepted wire forms correctly, then refresh the
  snapshot. Do not choose alias precedence, normalization, or field removal in this pilot.
  Existing core aliases remain in use until those resources migrate.
- OpenAPI omits Python default factories and behavioral validators. For example generated
  `ProfileResponse.persisted_domains` is optional `None`, whereas core supplies `[]`.
  A profile compatibility wrapper over the generated model should restore `[]` when absent
  before exposing `ProfileResponse`; tests must distinguish absent from explicit null.
  Request extras, pagination limits, viewport/proxy/cookie validation and defaults need
  resource-specific parity tests. Generated models retain constraints actually in the spec.
- Password formats generate `SecretStr`. Default Pydantic JSON serialization masks it;
  credential/action adapters must preserve the existing explicit secret-unwrapping policy
  at the transport boundary, while keeping repr/logs masked. Do not send masked values.

Nine used routes are absent from this snapshot. Their disposition is an open question, not
an approved removal plan. Recommendation: publish routes still in use and drop the rest in
v2, with backend coordination. Until decided they stay in the existing legacy boundary:

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

Run `uvx uv@latest sync --all-packages --all-extras`, then `make sdk-codegen` and commit all
artifacts. `make sdk-codegen-check` generates into a fresh temporary directory and compares
bytes, including the models' spec SHA256. It also runs the operation/resource freshness check.
Missing output fails too; the check does not overwrite files
or rely solely on `git diff`. Generation uses no API key, backend checkout or network schema
fetch. Versions are checked before running; Ruff matches pre-commit 0.11.10 and operates with
isolated configuration. The lock fixes transitive generator dependencies.

The `sdk-codegen` pre-commit hook covers model generation; `sdk-endpoints` checks all
operation/resource/typing outputs, the resource generator, compatibility and SDK source changes.
An explicit offline CI step runs the same check. Only the upstream-generated
`models.py` is ignored by basedpyright diagnostic reporting and its filename hook; generated
code still goes through Ruff, import checks and every-model JSON Schema construction.
Hand-written facade/generator code stays under the existing strict warning policy.

Keep `openapi_contract.py` (35 known drifts), existing endpoint checks and action-overload
checks unchanged during the parallel phase. Generated SDK models eventually need regeneration
and semantic/request-capture tests, not a second comparison against core's declarations.
Retire the SDK portion of that hand-written contract baseline as its consumers migrate;
keep a separate backend/core-to-published-spec release gate. Do not erase the baseline now
or grow it to excuse new generated drift. The production endpoint check now compares migrated
operations and their recursively referenced schemas too, including query defaults/constraints
and response changes, while ignoring documentation metadata (including examples). Schema
properties named `description`/`title` and literal defaults remain part of the contract.
Node now regenerates from this same committed snapshot
(`cd node-sdk && npm run generate`).
Its `npm run check:generated` compares fresh temporary output and checks the TypeScript
reference without a network spec fetch. After installing both toolchains, root
`make openapi-refresh` fetches staging and regenerates Python models/endpoints, Node
client/resources/proxy patterns and TypeScript docs; set `OPENAPI_URL=https://api.notte.cc`
for production. Commit all diffs together. The scheduled `openapi-bump.yml` proposes
one combined refresh PR for manual review; the former independent Node bump is removed.
The existing `nottelabs/notte` workflow guard and production release gate are unchanged.

## Migration order and size

1. **Merged #37:** design, pinned model generation, coverage and freshness gates. No public
   migration; no hand-written runtime savings.
2. **#42 base:** production snapshot refresh and both SDKs regenerated, plus `openapi-refresh`.
3. **This profiles pilot:** approved hybrid ownership, generated operation/invocation/keyword
   layers, reviewed wrappers and unchanged public create/get/delete/list behavior. The four
   facade methods still own docs and telemetry. This establishes infrastructure; it is not
   a net line-count reduction. Report additions/deletions separately for handwritten runtime,
   generated output, generator, tests, docs and configuration in the draft PR.
4. **Next:** migrate one simple resource using the same registry/index/generator, adding
   wrappers only for measured compatibility differences and writing request captures first.
   Vault metadata or usage can follow; credentials need secret/encryption review, personas
   have unpublished phone routes, and files have upload/download behavior.
5. **Then:** session management; functions and off-spec operations after backend schema/route
   decisions. Actions/observe/execute/scrape adapters are **not needed: shared core domain
   types**. Retire transitional core-bound resource factories as their last consumers migrate;
   retain core bindings for shared page operations. Async remains a separate additive project.

Earlier audit estimates (450–700 endpoint/factory lines movable and ~150–250 generator lines)
were planning estimates, not savings delivered by this pilot. Resource wrappers and retained
facade docs/telemetry reduce actual removals. Core's types module remains necessary for backend
and local sessions; none of its declarations count as SDK generation savings. Shared page-domain
ownership is approved; only the alias corrections and disposition of nine unpublished routes
remain open decisions.
