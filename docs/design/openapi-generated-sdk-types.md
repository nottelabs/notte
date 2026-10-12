# Generating the Python SDK wire types from the API's OpenAPI schema

Status: proposal, with a working prototype on branch `v2-openapi-types`.

## Summary

Generate the pydantic models (and kwargs TypedDicts) that mirror API schemas from the
API's `openapi.json` with **datamodel-code-generator**, into a private
`notte_sdk/_generated/` package. Keep `notte_sdk/types.py` as the public, hand-written
layer: each public model **subclasses** its generated model and adds only client-side
behavior. Commit a **snapshot** of the spec so generation and the drift check are
offline and deterministic; a scheduled workflow refreshes the snapshot from staging and
opens a PR, like `bump-node-sdk` does for the Node SDK.

Types stay in **notte-sdk**, not notte-core (see [Where generated types live](#where-generated-types-live)).

## Current state

### Node SDK

- `node-sdk/openapi-ts.config.ts` feeds `${NOTTE_API_URL:-https://us-staging.notte.cc}/openapi.json`
  to `@hey-api/openapi-ts`; output goes to `node-sdk/src/lib/client/` (`types.gen.ts` is
  ~11.9k lines, `sdk.gen.ts` ~1.1k).
- `npm run generate` = openapi-ts, then `scripts/normalize-generated.js` (LF, trailing
  whitespace, base URL pinned to `https://api.notte.cc`, detect-secrets pragmas), proxy
  patterns and `resources.gen.ts`.
- No spec snapshot is committed. The spec is public: no API key is needed, and staging
  and production served byte-identical specs on 2026-10-12 (285,936 bytes, `info.version` 1.9.7).
- Drift: `node-sdk-ci.yml` job `generated` runs `scripts/check-generated-drift.js`,
  which regenerates from **live staging** in a temp dir and compares the generated
  files. `node-sdk-bump.yml` regenerates 3x/day (05:00, 10:30, 14:00 UTC), opens
  `chore/bump-node-sdk`, and **auto-merges** once checks pass.
- Ergonomics: hand-written classes (`NottePersona`, `NotteSession`, ...) import the
  generated types and functions and hide them; options types are derived with
  `NonNullable<XData['query']>`.

### Python SDK

`packages/notte-sdk/src/notte_sdk/types.py` (2,421 lines on the base commit) is fully
hand-written:

| Kind | Count | Examples |
| --- | --- | --- |
| pydantic models | 94 | |
| of which (a) plain wire mirrors | 61 | `ProfileResponse`, `DeleteVaultResponse`, `SessionFile` |
| of which (b) wire + client behavior | 28 | `SessionResponse` (alias, validators, deprecated computed field), `EmailResponse.links()`, `ReplayResponse.download()`, `Cookie`, proxies, credentials requests, 9 function/run models with `AliasChoices("workflow_id", "function_id")`, `ListRequest`/`MessageReadRequest`/`PaginationParams` (client-side defaults) |
| of which (c) SDK-only | 5 | `SdkRequest`, `SdkResponse`, `_SessionStartRequest`, `LocalSessionStartRequest`, `ExecutionResponse` |
| TypedDicts (`**kwargs: Unpack[...]`) | 41 | `SessionStartRequestDict`, `PersonaCreateRequestDict` |
| StrEnums | 2 | `ProxyGeolocationCountry`, `FileSource` |

47 of the 94 models have a component schema of the same (or a known renamed) name.
Most of the others are query-parameter models (list filters) that have no component
schema, or local-only models.

Consumers outside notte-sdk: notte-browser imports `notte_sdk.types`
(`LocalSessionStartRequest(Dict)`, `PaginationParams(Dict)`, `ScrapeParams(Dict)`,
`ScrapeMarkdownParamsDict`, `Cookie`, `AspectRatio`, viewport constants, `EmailResponse`,
`SMSResponse`) and `notte_sdk.endpoints.personas.BasePersona`. notte-core and notte-llm
import nothing from notte-sdk.

### The backend imports these types today

`apps/back/notte-api` (monorepo, pinned to notte 1.x from git) imports
`notte_sdk.types` in ~43 non-test modules and builds many of its FastAPI models
**from** them, for example:

```python
class PersonaResponse(_SdkPersonaResponse):
    """Local extension of the SDK's `PersonaResponse` for API-only fields. [...]
    Once the external notte-sdk publishes these fields this class can be deleted [...]"""
    name: str | None = None
    created_at: dt.datetime
```

So today part of the spec is *derived from* the SDK, and drift appears wherever the
backend extends a model locally and nobody back-ports it. Generating the SDK from the
spec reverses that direction, so the API has to own its wire models (see Risks).

## Drift found (staging spec of 2026-10-12 vs hand-written models)

`scripts/sdk_types_drift_report.py` lists it; highlights:

| Model | Drift |
| --- | --- |
| `PersonaCreateRequest` | API accepts `name`; the SDK model has `extra="forbid"`, so `persona.create(name=...)` was **rejected client-side**. Fixed by the prototype. |
| `PersonaResponse` | API returns `name` and required `created_at`; SDK dropped them. Fixed by the prototype. |
| `ManagedAuthOperation` | API returns required `created_at`, `updated_at`; missing in SDK. |
| `ReplayResponse` | `expires_at` is required and non-null in the API, optional/nullable in the SDK. |
| `SessionStartRequest` | API accepts `demonstrate`; SDK can't send it. |
| `GetFunctionResponse` | 10 API fields missing (`published`, `required_secrets`, `source`, `self_healing`, `domain`, `instructions`, `response_format`, `schedule_cron`, `schedule_variables`, `schedule_state`). |
| `GetFunctionRunResponse` | missing `function_version`, `payloads`, `payload_urls`, `stopped_at`. |
| `FunctionRunUpdateRequest` | API accepts `payloads`, `result_preview`. |
| `RunFunctionRequest` and run responses | the wire still names fields `workflow_id`/`workflow_run_id`; the SDK exposes `function_id` via `AliasChoices`. `variables` is optional in the API, required in the SDK; `callback_url` missing. |
| `SessionResponse.status` | the backend's `SessionResponse` redeclares `status` without a description, so the schema lost "Session status" (visible in the regenerated SDK reference). |

## Generator choice

| Option | Verdict |
| --- | --- |
| **datamodel-code-generator 0.83** | **Chosen.** Pydantic v2 models, `Annotated[..., Field(...)]`, `Literal` enums, `X \| None`, discriminated unions emitted as `Field(discriminator="type")`, deterministic output (`--disable-timestamp`, `--keep-model-order`), TypedDict output (`--output-model-type typing.TypedDict`, `--use-total-false-for-typed-dict` gives the `total=False` + `Required[...]` style our kwargs dicts use), per-field `--type-overrides`, `--import-overrides`. Run via `uvx` at a pinned version: no runtime or dev dependency. Generated code passes basedpyright 1.27.1 (repo config, `failOnWarnings`) with zero findings. |
| openapi-python-client | Rejected. Generates a whole httpx client with **attrs** classes (259 model files, ~160 lines each with hand-rolled `to_dict`/`from_dict`), `UNSET` sentinels, adds `httpx`/`attrs` runtime deps; warns on some of our schemas. |
| OpenAPI Generator (python) | Rejected. JVM tool, one file per model, own runtime (`urllib3`, `python-dateutil`), verbose. |
| fastapi-code-generator | Server stubs; uses datamodel-code-generator underneath anyway. |
| Stainless / Speakeasy / Fern | Hosted, paid, own the whole client; overkill for "types only". |

Flags used (see `scripts/generate_sdk_types.py`):

```
--input-file-type openapi --target-python-version 3.11
--output-model-type pydantic_v2.BaseModel --use-annotated --field-constraints
--use-schema-description --use-union-operator --use-standard-collections
--enum-field-as-literal all --collapse-root-models --strict-nullable
--output-datetime-class datetime --use-double-quotes --disable-timestamp
--keep-model-order --formatters builtin
--type-overrides '{"SessionResponse.duration": "datetime.timedelta"}'
# TypedDict pass:
--output-model-type typing.TypedDict --no-use-closed-typed-dict
--use-total-false-for-typed-dict --import-overrides '{TypedDict,NotRequired,Required -> typing_extensions}'
```

`--strict-nullable` matters: without it every field with a default becomes `X | None`.
The output is then formatted with **the ruff version pinned in `.pre-commit-config.yaml`**
(read from that file), so pre-commit never rewrites generated files and regeneration is
byte-for-byte reproducible.

### Spec normalization (before generation)

The script generates from a pruned, normalized copy of the snapshot:

1. **Allowlist + closure.** Only `RESPONSE_SCHEMAS`/`REQUEST_SCHEMAS` and everything they
   `$ref` are generated (12 models today). A full-spec module is 197 classes and costs
   ~72 ms to import vs ~5 ms for the subset, and would ship agents, payments, mailbox and
   audit models the v2 SDK does not expose.
2. **Drop property `title`s**: FastAPI derives them from the field name; pure noise.
3. **Drop deprecated read-only properties** (`SessionResponse.timeout_minutes` is a server
   computed field). Generated as a required field it would clash with the SDK's deprecated
   computed property.
4. **Rewrite `anyOf: [{integer, minimum: 500}, {null}]` as `type: [integer, null]`.**
   Otherwise datamodel-codegen emits `RootModel` classes (`viewport_width: ViewportWidth | None`)
   that users would have to construct.

## Where generated types live

**notte-sdk (`notte_sdk/_generated/`), not notte-core.**

- The spec describes the HTTP API, which is the SDK's concern. notte-core is shared
  models/actions/config, depends only on pydantic & co, and must stay lightweight
  (Pyodide constraint on aiohttp; import time matters).
- Several schemas in the spec are **produced from notte-core** classes (actions,
  `Observation`, `DataSpace`, `NodeSelectors`, `TabsData`, credentials dicts). Generating
  them back into core would create a cycle with the source of truth. When a migrated
  model references one, map it to the core class with `--type-overrides`
  (e.g. `{"GotoAction": "notte_core.actions.GotoAction"}`) instead of duplicating it.
- notte-browser already depends on notte-sdk and only imports public names from
  `notte_sdk.types`, which do not move.
- `_generated` is private. Public import paths stay `notte_sdk.types.X`.

## How the hand-written layer composes

Subclass, don't wrap (the Node SDK wraps because TS types are erased; in Python the
models are returned to users and must stay `isinstance`-compatible):

```python
from notte_sdk._generated import models as wire
from notte_sdk._generated import typeddicts as wire_dicts

class PersonaCreateRequestDict(wire_dicts.PersonaCreateRequest, total=False):
    """Request dictionary for creating a new persona (generated from the API schema)."""

class PersonaCreateRequest(wire.PersonaCreateRequest, SdkRequest): pass
class PersonaResponse(wire.PersonaResponse, SdkResponse): pass

class EmailResponse(wire.EmailResponse, SdkResponse):
    def links(self) -> list[str]: ...

class SessionResponse(wire.SessionResponse, SdkResponse):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")
    idle_timeout_minutes: Annotated[int, Field(validation_alias=AliasChoices("idle_timeout_minutes", "timeout_minutes"))]
    duration: Annotated[dt.timedelta, ...] = Field(default_factory=...)  # pyright: ignore[reportIncompatibleVariableOverride]
    # validators, deprecated computed timeout_minutes, legacy headless property
```

Rules:

- A public model may add methods, validators, computed fields, aliases and narrower
  types; it never drops a wire field (`tests/sdk/test_generated_types.py` enforces it).
- Requests keep `extra="forbid"` (from `SdkRequest`), responses ignore or allow unknown
  fields, so an SDK keeps working when the API adds fields.
- Overriding a field's type is a deliberate divergence; pyright flags it
  (`reportIncompatibleVariableOverride`, mutable fields are invariant), so it carries an
  explicit ignore. Prefer fixing it upstream: a generation-time `--type-overrides` entry
  (done for `duration`), or a backend schema change (e.g. declare `steps: list[...] = []`
  instead of `default_factory=list`, so the spec carries the default).
- Field order, docstrings and `__module__` of the public class are preserved, so the
  Sphinx reference and `test_no_orphan_models` keep working.

## Pipeline and checks

| Piece | Prototype |
| --- | --- |
| Snapshot | `packages/notte-sdk/openapi/openapi.json` (pretty JSON, server key order; not in the wheel) |
| Generate | `make sdk-types` (`scripts/generate_sdk_types.py`) |
| Refresh snapshot | `make sdk-types-fetch [SDK_TYPES_URL=https://api.notte.cc]` (default staging) |
| Offline drift check | `make sdk-types-check`; also a pre-commit hook (`sdk-types-check`), so `test-cicd`'s `pre-commit run --all-files` enforces it with no network |
| Live drift | `.github/workflows/python-sdk-types-bump.yml`: 3x/day, fetch staging, regenerate, run basedpyright + SDK type tests, open/refresh `chore/bump-python-sdk-types` with the hand-written drift report, and **auto-merge** once checks pass (like bump-node-sdk) |
| Release gate | `make sdk-types-check-prod` in `pypi-release.yml`: regenerate from `https://api.notte.cc` and fail on diff, so a release never requires fields production doesn't serve yet |
| Remaining drift | `scripts/sdk_types_drift_report.py` (informational) |

Why a snapshot, unlike the Node SDK: PR checks stay hermetic (a staging deploy does not
turn every open PR red), the spec change is reviewable in the bump PR, and releases are
reproducible. Staging->SDK loop for a developer: change the API, deploy to staging, run
`make sdk-types-fetch`, fix the hand-written layer if pyright/tests complain, commit.

## Migration plan (small PRs, in order)

1. **Tooling** (prototype commit 1): script, snapshot, `_generated`, make targets,
   pre-commit check. No public change.
2. **Personas + `SessionResponse`** (prototype commit 2, plus tests): proves the pattern.
   Public additions: `PersonaResponse.name/.created_at`, `PersonaCreateRequest.name`.
3. **Bump workflow** (prototype commit 4). Enable once the snapshot is on `main`.
4. **Plain responses** (category a, ~40 models): profiles, vaults/credentials/credit-card
   responses, files, cookies, debug/replay responses, `ManagedAuthOperation`
   (gains `created_at`/`updated_at`). Mostly `class X(wire.X, SdkResponse): pass`.
5. **Query-parameter models**: add a normalization step that synthesizes component
   schemas from operations' query parameters (named from `operationId`), so list
   requests and their kwargs TypedDicts (`PersonaListRequestDict`, `SessionListRequestDict`, ...)
   are generated too. Keep client-side defaults (`page_size=10`) in the subclasses.
6. **Session start**: `SessionStartRequest(Dict)` on `ApiSessionStartRequest` (gains
   `demonstrate`); keep `_SessionStartRequest`/`LocalSessionStartRequest` hand-written
   for notte-browser. Proxies are already generated as a discriminated union; decide
   whether `ProxyGeolocationCountry` stays a StrEnum or becomes the generated `Literal`.
7. **Functions/runs**: needs the `workflow_id` -> `function_id` decision (see Risks):
   ideally the API renames the wire fields first, then these become plain subclasses.
8. **Execution/observe**: map core-owned schemas with `--type-overrides`; the `-Input`/`-Output`
   duplicates (20 schemas) should be removed server-side first.
9. **Cleanup**: once most models are generated, the drift report lists only SDK-only
   models; consider making `test_dict_types`' source-regex checks structural.

## Risks

- **Breaking public types.** Generated required fields make the SDK stricter: code that
  constructs `PersonaResponse(...)` by hand (tests, mocks, notte-browser stubs) must now pass
  `created_at` (one test fixture changed). Field removals in the API become removals in
  the SDK; the bump PR auto-merges once checks pass, so the typecheck/tests and the production release gate are the guard.
- **Staging ahead of production.** Generating from staging can make the SDK require a
  field production does not send yet. Release gate (done): before publishing to PyPI,
  `make sdk-types-check-prod` regenerates against `https://api.notte.cc` and fails on diff (the old
  `tests/sdk/test_openapi_spec.py` compares staging vs prod but points at the legacy
  `staging.notte.cc` host).
- **Backend imports SDK types.** While notte-api builds its models from `notte_sdk.types`,
  generated SDK types close a loop (spec -> SDK -> backend -> spec): removing a field
  needs a backend override first. v2 already requires pinning notte-api to a 1.x SHA, so
  the loop does not exist for v2; long term the API should own its wire models and import
  only notte-core.
- **Aliases and legacy names.** Generated models use wire names (`workflow_id`). Keeping
  `function_id` public needs a field rename in the subclass, which pydantic does not do
  cleanly; prefer renaming on the server (with a deprecated alias there).
- **Defaults.** Server defaults set via `default_factory` are invisible in the spec
  (`steps`, `duration`), and some client defaults deliberately differ (`ListRequest.page_size=10`,
  viewport defaults from `config`). These stay as overrides in the hand-written layer.
- **Discriminated unions.** Handled (`Field(discriminator="type")` on proxies), but actions
  appear as `-Input`/`-Output` pairs because FastAPI splits schemas; those should map to
  notte-core classes, not be generated.
- **Docs generation.** The Sphinx reference renders field descriptions, so doc quality now
  follows the API schema (the `SessionResponse.status` description regressed). `NotRequired[...]`
  leaked into rendered kwargs until the TypedDicts were generated with `total=False`.
- **Tooling drift.** datamodel-code-generator and ruff versions are pinned; bumping either is
  a regeneration PR. The generator needs `uvx` (and network on first run) in CI.
- **Source-regex tests.** `tests/sdk/test_dict_types.py` parses `types.py` text; it was taught
  that a `wire_dicts.` base is a TypedDict.

## Decisions (2026-10-12)

1. The bump PR auto-merges once its checks pass, like bump-node-sdk.
2. Staging feeds the bump PR; production is the release gate (`make sdk-types-check-prod`).
3. notte-api renames `workflow_id` to `function_id` on the wire (keeping `workflow_id` as a
   deprecated duplicate while 1.x SDKs are in use) before the functions step.
4. The Node SDK moves to a committed snapshot too, so both SDKs pin the same spec.

## Open questions

1. Can notte-api stop splitting schemas into `-Input`/`-Output` pairs
   (`separate_input_output_schemas=False`) before the actions step?
2. Keep `ProxyGeolocationCountry` as a public StrEnum, or expose the generated `Literal`?
