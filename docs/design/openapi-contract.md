# One source of truth for the API wire models

Status: in progress (branch `v2-openapi-types`). Decided on 2026-10-12.

## Summary

The pydantic models that describe the Notte API's requests and responses live in
**`notte_core.types`**. They are the single source of truth:

```
notte_core.types ──► notte-api (FastAPI) ──► openapi.json ──► node-sdk (generated)
        │
        └──► notte-sdk (`notte_sdk.types` re-exports them), notte-browser
```

- **notte-api** imports these models for its endpoints, and FastAPI renders them into
  `openapi.json`. The API changes a model by changing it in notte (the backend's daily
  dependency bump picks it up), never by subclassing or redeclaring it locally.
- **The Python SDK** uses the same classes, so it can't drift from the API. Nothing is
  generated for Python. `notte_sdk.types` stays a public re-export, so imports keep working.
- **The Node SDK** is generated from `openapi.json`, as today.
- **A contract check** catches the remaining drift: the API extending or redeclaring a
  model instead of changing it here.

## Why not generate the Python SDK from `openapi.json`

About 43 notte-api modules import their models from `notte_sdk.types`, so the spec is
built from the SDK's own models. Generating the SDK from the spec would be circular:
`types.py → notte-api → openapi.json → generated types → types.py`. The drift we saw comes from
the backend extending SDK models locally instead of changing them upstream, for example:

```python
class PersonaResponse(_SdkPersonaResponse):
    """Local extension of the SDK's `PersonaResponse` for API-only fields. [...]
    Once the external notte-sdk publishes these fields this class can be deleted [...]"""
    name: str | None = None
    created_at: dt.datetime
```

Moving the models to notte-core and making the API use them as-is removes that loop. The
alternative (the API owns its models in the monorepo, and both SDKs are generated from the
spec) would mean rewriting those backend modules and maintaining a Python code generator.

## Pieces

| Piece | Where |
| --- | --- |
| Wire models | `packages/notte-core/src/notte_core/types.py` (moved from `notte_sdk/types.py`; `notte_sdk.types` re-exports it) |
| Spec snapshot | `openapi/openapi.json` at the repo root, so node-sdk can use the same file |
| Contract check | `scripts/openapi_contract.py --check`: diffs every model against the schema of the same name (fields, required, nullable). Known drift is listed in `openapi/known_drift.txt`; anything new fails. Runs as the `openapi-contract` pre-commit hook, so CI enforces it offline |
| Staging refresh | `.github/workflows/openapi-bump.yml`, 3x/day like bump-node-sdk: fetch the staging spec, open or refresh `chore/bump-openapi`, and auto-merge once checks pass. When the API drifted, the PR's contract check fails and the PR stays open |
| Release gate | `make openapi-check-prod` in `pypi-release.yml`: run the contract check against `https://api.notte.cc` before publishing |
| Make targets | `make openapi-check`, `make openapi-fetch [OPENAPI_URL=...]`, `make openapi-check-prod`; `--update-baseline` records drift on purpose |

## Developer loop

1. Change the model in `notte_core.types` (new field, new request) and merge it in notte.
2. notte-api picks it up (daily dependency bump, or bump it in the same change) and uses
   the model in its endpoint.
3. Deploy to staging. The next `openapi-bump` run refreshes the snapshot; the contract
   holds, so the PR merges itself and the Node SDK regenerates from the same schema.

If the API ships a field without step 1, the refresh PR fails the contract check and
shows exactly which model drifted.

## Known drift (staging, 2026-10-12)

44 entries in `openapi/known_drift.txt`, mostly:

| Model | Drift |
| --- | --- |
| Function and function-run models | the wire still says `workflow_id` / `workflow_run_id`; the models expose `function_id`. `GetFunctionResponse` lacks 10 API fields (`published`, `required_secrets`, `source`, `schedule_*`, ...), `GetFunctionRunResponse` lacks `function_version`, `payloads`, `payload_urls`, `stopped_at` |
| `RunFunctionRequest` | `callback_url` missing; `variables` optional in the API, required here |
| `ManagedAuthOperation` | API returns required `created_at`, `updated_at` |
| `ReplayResponse` | `expires_at` required in the API, optional here |
| `SessionStartRequest` | API accepts `demonstrate` |
| `SessionResponse` | the API names `idle_timeout_minutes` `timeout_minutes` |

Fixed while building this: `PersonaCreateRequest.name` (the SDK rejected
`persona.create(name=...)` before sending it) and `PersonaResponse.name` / `created_at`.

## Migration plan

1. **This PR**: move the models to notte-core, add the snapshot, contract check,
   staging refresh and release gate.
2. notte-api: rename `workflow_id` → `function_id` on the wire, returning both while 1.x SDKs
   are in use and accepting both in requests; then drop the function entries from the baseline.
3. Shrink the baseline: add the missing fields to the models here, then delete the
   backend's local subclasses (`PersonaResponse`, ...) so it imports `notte_core.types` directly.
4. node-sdk: generate from `openapi/openapi.json` instead of live staging, so both SDKs and
   their CI pin the same spec; merge the two refresh workflows.
5. Split `notte_core.types` by resource (sessions, personas, vaults, functions, files,
   profiles, scrape) once the move has settled.

## Risks

- **Stricter models.** Adding API-required fields (e.g. `PersonaResponse.created_at`)
  breaks code that builds these models by hand (tests, mocks).
- **Staging ahead of production.** The release gate blocks a PyPI release whose models
  production doesn't serve yet.
- **Backend on 1.x.** notte-api still pins notte 1.x, where the models live in
  `notte_sdk.types`. Its move to v2 must switch its imports to `notte_core.types` and
  delete its local model extensions (step 3).
- **`-Input` / `-Output` schemas.** FastAPI splits a model used in both directions into two
  schemas; the contract check matches either name.
