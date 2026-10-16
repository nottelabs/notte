# SDK generation ownership

Both SDKs generate public resource methods from the committed `openapi/openapi.json`
and shared `openapi/resources.json`. Node's camelCase names are canonical; Python
converts them to snake_case. Every spec operation must be mapped or explicitly
excluded. Both generators reject uncovered or stale mappings. Python's resource
membership is derived from this table, with explicit `pythonImplementation` reasons
for the page, multipart, binary IO and streaming exceptions.

Python's generated methods own API summary/description docstrings, telemetry event
names and list-item unwrapping. `pythonUnwrapItems` preserves the existing Python
list results; function listings keep their page envelopes. Node retains its existing
method names and session-file entry points, and also exposes `client.files`.
The table's Node aliases retain that existing public surface, rather than introduce
deprecated Python aliases. Breaking Python renames are in
`packages/notte-sdk/CHANGELOG.md`.

## Hybrid model ownership

`datamodel-code-generator==0.83.0` generates plain Pydantic models, query models and
inline bodies. Its enum options are `--enum-field-as-literal all`,
`--use-specialized-enum` and `--capitalise-enum-members`; named component enums opt
out of literal generation in temporary generator input. The committed spec is not
modified by generation.

`CORE_MODELS` and `MODEL_OVERRIDES` in `scripts/generate_sdk_endpoints.py` map schema
names to core imports for existing behavior: session requests/responses, proxies,
cookies, profile configuration, credentials, function response aliases and nested
metadata, email links, replay downloads, debug websocket URLs and managed-auth
readiness. Page actions, observations, execution and structured scrape data stay
in core and continue to use `PageClient`, shared with local sessions. Generated
plain copies remain private coverage artifacts and are not substituted at these
public boundaries.

Explicit validated core construction retains its validation. Cloud resource calls
use raw request serialization and send caller fields, including invalid values,
to API validation. Opt-in core `from_raw` construction preserves nested cookie,
profile and proxy objects without running business validators. Known proxy-country
strings become enum members, preserving string equality and `.value`. Unknown
values remain transportable for server rejection. SDK response context bypasses
credential identity business validation while preserving response schema checks.

The existing `scripts/openapi_contract.py --check` guards core/spec drift; the 35
existing entries are unchanged. Core raw serialization additions count as runtime
code in the revision report, even though they are outside the SDK package.

## Handwritten boundaries

Resource clients retain only IO, orchestration and unpublished routes. Stateful
`NottePersona`, `NotteVault`, `RemoteSession`, `NotteFunction` and `RemoteFileStorage`
keep lifecycle, polling, local files and convenience logic. API-only JSON methods
such as vault update, profile duplication/cookies and function schedules are
generated directly from the shared table, without handwritten forwarding methods.

The remaining compatibility module classes have runtime effects:

- Profiles: non-null independently allocated domain lists, required deletion
  status/message, and public list defaults/excluded SDK-only query fields.
- Run payloads: string upload IDs and the nested response reference shape used by
  the integrity-check/upload path.

Matching request defaults are omitted. Retained Python differences are profile
page size 20 (API 10), active-only function run lists, local browser configuration,
and managed-auth wait control. Node keeps its existing all-run list default.

Python page methods remain on `PageClient`; Node exposes them on its cloud session
resource. Function execution and file transfer have the same canonical method
names but language-specific streaming/file signatures. Node binary downloads force
blob parsing, so text/JSON files retain their bytes.

## Unpublished routes

Backend should publish these routes; none is added to the committed spec here:

- `POST` and `DELETE /personas/{id}/sms/number`.
- `GET /sessions/{id}/debug/tab`.
- `POST /functions/{id}/runs/create` and `POST /functions/{id}/runs/{run_id}`.
- `POST /managed-auth/connections/{id}/check`, `/refresh`, `/reauthenticate`.
- `GET /managed-auth/operations/{id}`.

## Generation and gates

`make sdk-codegen` generates Python models and endpoints from the committed spec.
`make sdk-codegen-check` verifies freshness and contracts. Node uses `npm run
generate --prefix node-sdk`, typecheck and unit tests. `npm run docs:generate
--prefix node-sdk` updates TypeScript references; `npm run docs:check --prefix
node-sdk` verifies them. Both Python and Node codegen checks enforce naming coverage.

Run pinned all-files pre-commit, `make docs-check`, and `python -m unittest discover
-s docs/src/sniptest -p 'test_*.py'`, plus the offline Python suite and matching
staging integration tests. Docs examples remain paired under `docs/src/testers`.
Keep the spec unchanged for this revision; a later OpenAPI refresh must regenerate
both SDKs and references together.
