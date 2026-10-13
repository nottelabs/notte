# Node SDK vs Python SDK parity

Audit of `node-sdk/` against `packages/notte-sdk/` (Python, version 1.4.4.dev).
Mark the first **Port** column with ✅ (port it) or ❌ (leave out). Use the **Decision** column for notes.

Legend for Priority: **P0** correctness or security, **P1** commonly used Python feature, **P2** nice to have, **P3** endpoint neither SDK wraps.

---

## 1. Correctness and behavior fixes (existing Node surface)

| Port | # | Item | Details | Python reference | Priority | Decision |
|---|---|------|---------|------------------|----------|----------|
| ✅  | 1.1 | Scrape guesses `instructions` from schema text | `client.scrape` and `session.scrape` substring-match the serialized JSON schema for `plans`, `products`, `articles` and inject invented instructions when none are given. `node-sdk/src/client.ts:182`, `node-sdk/src/session.ts:413` | Python passes `response_format` and `instructions` through untouched | P0 | |
| ✅  | 1.2 | Generated singleton `client` hardcodes staging URL | `node-sdk/src/lib/client/client.gen.ts:16` sets `baseUrl: 'https://us-staging.notte.cc'`. This singleton is re-exported from `index.ts`, so `import { client } from 'notte-sdk'` talks to staging. | Python default is `https://api.notte.cc` | P0 | |
| ✅  | 1.3 | `vault.getCredentials()` swallows all errors and returns `null` | Auth failures, network errors and "not found" are indistinguishable. `node-sdk/src/vaults.ts:166` | Python raises `NotteAPIError` | P0 | |
| ❌  | 1.4 | `persona.createNumber()` / `deleteNumber()` documented but do not exist | Listed in `README.md:419-420`, used in `examples/persona.ts:113,118`. No wrapper and no generated operation for `POST/DELETE /personas/{id}/sms/number`, so OpenAPI regeneration may be needed too. | `NottePersona.create_number`, `delete_number` | P0 | this is a deprecated feature, we'should just remove them it from the documentation |
| ✅  | 1.5 | `execute()` failures lose the typed exception | Node throws `Error("Action execution failed: <message>")`. `node-sdk/src/session.ts:314` | Python rehydrates `exception_detail` into the concrete error class, with fallback to `NotteBaseError` | P1 | |
| ✅  | 1.6 | Structured scrape has no `raise_on_failure` contract | Node returns whatever the API returns. | Python: default raises `ScrapeFailedError` and returns the unwrapped model; `raise_on_failure=False` returns `StructuredData` with `.success` | P1 | |
| ✅  | 1.7 | Session replay after `stop()` | `stop()` clears the active ID. `replay()` falls back to `response.session_id` but has no polling. Tracked in `test/INTEGRATION_BACKLOG.md`. | Python `replay(wait=True, timeout=240, poll_interval=5)` polls on 404 until the recording is finalized, and raises if the session is still active | P1 | |
| ✅  | 1.8 | Version check is dead code | `startVersionCheck` in `node-sdk/src/version-check.ts:22` is never called nor exported. Only `checkForLatestVersion` is exported and must be invoked manually. | Python warns once per process on a stale version, skipping `.dev` builds | P2 | we should have the same as in python |
| ✅  | 1.9 | `agent.isRunning()` is misleading | Returns `response !== null`, not the live status. `node-sdk/src/agent.ts:597` | No equivalent; Python uses `status()` | P2 | |
| ✅  | 1.10 | Function `run()` requires a raw API key even in proxy mode | `node-sdk/src/functions.ts:197` | n/a | P2 | we should have the same as in python |
| ✅  | 1.11 | `SessionFiles` bypasses the generated file operations | Uses raw `client.request()` with hand-declared types because staging OpenAPI lags. `node-sdk/src/files.ts:3` | n/a | P2 | |

---

## 2. Client infrastructure

| Port | # | Item | Details | Python reference | Priority | Decision |
|---|---|------|---------|------------------|----------|----------|
| ✅  | 2.1 | Typed error hierarchy | Node has one class, `NotteProxyAuthError`. Everything else is a bare `Error` with a string prefix. Callers cannot branch on status code or catch by class. | `NotteAPIError` (with `.status_code`, `.error`), `NotteAPIExecutionError` (via `x-error-class` header), `AuthenticationError`, `InvalidRequestError`, `FailedToRunCloudFunctionError` | P0 | |
| ✅  | 2.2 | Retries and backoff | None anywhere in `src/`. | Session start retries 3x on 5xx and waits 30 s on HTTP 529; captcha-solve retries 3x on 408; replay polls on 404; public `retry` decorator | P1 | we should have the same as in python |
| ✅  | 2.3 | Configurable request timeouts | Hardcoded constants only: agent poll deadline 300 s, function download 30 s, version check 1.5 s. `Agent.status()` accepts an `AbortSignal`, nothing else does. | `DEFAULT_REQUEST_TIMEOUT_SECONDS = 60`, per-request `timeout` override, 100 s for captcha actions | P1 | |
| ✅  | 2.4 | `health_check()` on the client | `healthCheck` / `readyCheck` exist in the generated layer but are not wrapped. | `NotteClient.health_check()` | P2 | we should have the same as in python |
| ✅  | 2.5 | DB preview branch support | No `NOTTE_DB_PREVIEW_BRANCH` env var, no `x-db-preview` header, no `db_preview` query param on websocket URLs. | `BaseClient.db_preview`, `_with_db_preview(url)` | P2 | we should have the same as in python |
| ✅  | 2.6 | Non-default server URL warning | Node validates HTTPS but does not warn. | Python logs a warning when `NOTTE_API_URL` differs from the default | P3 | we should have the same as in python |
| ✅  | 2.7 | Upgrade hint on 422 validation errors | n/a | Python detects pydantic-style 422 responses and suggests `pip install notte-sdk==X` when a newer version exists | P3 | we should have the same as in python |

---

## 3. Sessions and page control

| Port | # | Item | Details | Python reference | Priority | Decision |
|---|---|------|---------|------------------|----------|----------|
| ✅  | 3.1 | Typed action builders and `execute()` typing | `execute(action: any)`. Generated types such as `ClickActionInput`, `GotoAction`, `FillActionInput` exist in `types.gen.ts` but are unused. | 28 typed `execute` overloads plus exported action classes: `Click`, `Fill`, `Goto`, `GotoNewTab`, `CloseTab`, `SwitchTab`, `GoBack`, `GoForward`, `Reload`, `Wait`, `PressKey`, `ScrollUp`, `ScrollDown`, `Check`, `SelectDropdownOption`, `UploadFile`, `DownloadFile`, `FormFill`, `MultiFactorFill`, `FallbackFill`, `CaptchaSolve`, `EmailRead`, `EmailVerificationRead`, `SmsRead`, `EvaluateJs`, `Scrape`, `Help`, `Completion` | P1 | |
| ✅  | 3.2 | `evaluateJs(code)` | Not present. | `RemoteSession.evaluate_js(code, raise_on_failure=True) -> str` | P1 | |
| ✅  | 3.3 | `fetch()` from inside the page | Not present. Runs an HTTP request in the browser context with page cookies, proxy and fingerprint. | `RemoteSession.fetch(url, method, headers, params, json, data, timeout) -> Response` | P1 | |
| ✅  | 3.4 | `cdpUrl()` accessor | Users read `status().cdp_url` manually. `sessionDebugInfo` is only used internally by `Agent`. | `RemoteSession.cdp_url` (prefers external `cdp_url`, then `response.cdp_url`, then `debug_info().ws.cdp`) | P1 | |
| ✅  | 3.5 | Playwright bridge | `playwright-core` is a dev dependency only. No helper to connect over CDP. | `session.page` (sync) and `await session.apage` (async), lazily connected and cached, with server-owned dialog policy | P1 | could we no make python a dependency of node-sdk ?it's tecnnically no needed right ? could we make it optional like we have in python ? i.e pip install notte-sdk[playwright]|
| ❌  | 3.6 | `observe(instructions)` returning a filtered action list | Node `observe(perceptionType)` only. | `observe(instructions=..., perception_type=..., min_nb_actions, max_nb_actions)` returns `list[InteractionActionUnion]` when instructions are set | P1 | |
| ❌  | 3.7 | `offset()` | `sessionOffset` unwrapped. Needed for `session_offset` on agent runs. | `RemoteSession.offset()` | P2 | |
| ✅  | 3.8 | `debugInfo()` / `debugTabInfo()` | Unwrapped publicly. | `debug_info()`, `debug_tab_info(tab_idx)` | P2 | |
| ✅  | 3.9 | `listSessions` | `listSessions` unwrapped. | `client.sessions.list(only_active, page, page_size, include_system)` | P2 | |
| ✅  | 3.10 | Cookie export to file | Node has `setCookiesFromFile` but no export. | `cookie_file` constructor option persists cookies on `stop()`; `Cookie.from_json` / `dump_json` | P2 | |
| ✅  | 3.11 | Replay download helper | `replay()` returns the response only. | `ReplayResponse.download(path="replay.mp4")` | P2 | |
| ❌  | 3.12 | Viewer variants | Node opens `viewer_url` only. | `viewer_browser()`, `viewer_cdp()`, `viewer_notebook()` and client-level `viewer_type` | P3 | |
| ❌  | 3.13 | Proxy config helpers | Raw objects only. | `NotteProxy.from_country`, `NotteProxy.from_city`, `ExternalProxy.from_env`, `TailnetProxy` | P2 | |
| ❌  | 3.14 | `pageScreenshot` | Unwrapped (neither SDK wraps it). | n/a | P3 | |
| ❌  | 3.15 | `sessionNetworkLogs` | Unwrapped (neither SDK wraps it). | n/a | P3 | |
| ✅  | 3.16 | `getSessionScript` (`/sessions/{id}/workflow/code`) | Unwrapped. | n/a | P3 | |

---

## 4. Agents

| Port | # | Item | Details | Python reference | Priority | Decision |
|---|---|------|---------|------------------|----------|----------|
| ❌  | 4.1 | AgentFallback | No equivalent. Context manager that wraps `execute` calls and spawns an agent with the original task when a step fails. | `RemoteAgentFallback` in `agent_fallback.py` | P1 | |
| ❌  | 4.2 | Public `watchLogs()` / `watchLogsAndWait()` | Log streaming is private and only reachable through `run()` with `updateHandler`. | `RemoteAgent.watch_logs(log)`, `watch_logs_and_wait(log)`, `async_watch_logs_and_wait` | P1 | |
| ❌  | 4.3 | `wait()` | Not present. Polling with spinner until completion. | `RemoteAgent.wait()` (`polling_interval_seconds=10`, `max_attempts=30`) | P2 | |
| ❌  | 4.4 | Agent function code export | `getScript` (`/agents/{id}/workflow/code`) unwrapped. | `agent.workflow.code(as_workflow)` and `agent.workflow.create_function()` | P2 | |
| ❌  | 4.5 | `listAgents` | Unwrapped. | `client.agents.list(only_active, only_saved, page, page_size)` | P2 | |
| ❌  | 4.6 | `agent.replay()` | Not present. Deprecated in Python in favor of `session.replay()`. | `RemoteAgent.replay()` | P3 | |
| ❌  | 4.7 | Context manager `use()` on Agent | Session and Persona have `use()`, Agent does not. | n/a (Python agents are not context managers) | P3 | |
| ❌  | 4.8 | Proxy-mode agents cannot stream logs | Relative-URL proxy clients fall back to 1 s status polling. Documented limitation. `node-sdk/src/agent.ts:399` | n/a | P3 | |


---------> GLOBAL SUMMARY: buttom line lets not do any work on this, let's just remove all notteAgent from the node-sdk because they are deprecated in python and we don't need them in node-sdk

---

## 5. Functions

| Port | # | Item | Details | Python reference | Priority | Decision |
|---|---|------|---------|------------------|----------|----------|
| ✅  | 5.1 | Create function from local file | `functionCreate` unwrapped. | `client.functions.create(path, name, description, shared)` and `NotteFunction(path=...)` | P1 | |
| ✅  | 5.2 | `update()` | `functionUpdate` / `functionMetadataUpdate` unwrapped. | `NotteFunction.update(path, version, restricted)` | P1 | |
| ✅ | 5.3 | `delete()` | `functionDelete` unwrapped. | `NotteFunction.delete()` | P1 | |
| ✅  | 5.4 | `list()` | `listFunctions` unwrapped. | `client.functions.list(...)` | P1 | |
| ❌  | 5.5 | `stopRun()` | `functionRunStop` unwrapped. Runs cannot be cancelled through the wrapper. | `NotteFunction.stop_run(run_id)` | P1 | |
| ❌  | 5.6 | `fork()` | `functionFork` unwrapped. | `NotteFunction.fork()` | P2 | |
| ❌  | 5.7 | `updateRun()` | `functionRunUpdateMetadata` unwrapped. | `client.functions.update_run(function_id, run_id, ...)` | P2 | |
| ❌  | 5.8 | `getCurl()` | Not present. | `NotteFunction.get_curl(**variables)` | P2 | |
| ❌  | 5.9 | `replay()` on function | Not present. | `RemoteWorkflow.replay()` | P3 | |
| ❌  | 5.10 | Local execution | Not present. | `run(local=True)` via `SecureScriptRunner` + `LogCapture` | P3 | |
| ✅  | 5.11 | Schedules and rollback | `functionScheduleSet`, `functionScheduleDelete`, `functionRollback` unwrapped (neither SDK wraps them). | n/a | P3 | |
| ❌  | 5.12 | `functionRuntimeHealth` | Unwrapped (neither SDK wraps it). | n/a | P3 | |
| ✅  | 5.13 | Hand-rolled non-OpenAPI endpoints | `POST /functions/{id}/runs/create` and `POST /functions/{id}/runs/{run_id}` are not in the spec and are called via raw `client.post`. `node-sdk/src/functions.ts:128,223` | Python uses the same paths | P3 | |

---

## 6. Vaults

| Port | # | Item | Details | Python reference | Priority | Decision |
|---|---|------|---------|------------------|----------|----------|
| ✅  | 6.1 | `listVaults` | Unwrapped. | `client.vaults.list(...)` | P2 | |
| ❌  | 6.2 | `vaultUpdate` | Unwrapped (neither SDK wraps it). | n/a | P3 | |
| ✅  | 6.3 | `hasCredential(url)` | Not present. | `BaseVault.has_credential(url)` | P3 | |
| ❌  | 6.4 | Context manager `use()` on Vault | Not present. | `NotteVault` is a `SyncResource`; `stop()` deletes the vault | P3 | |

---

## 7. Personas

| Port | # | Item | Details | Python reference | Priority | Decision |
|---|---|------|---------|------------------|----------|----------|
| ❌  | 7.1 | Phone number create / delete | See 1.4. | `create_number(**opts)`, `delete_number()` | P0 | |
| ❌ | 7.2 | `personaUpdate` | Unwrapped (neither SDK wraps it). | n/a | P3 | |
| ❌  | 7.3 | Mailboxes | 6 generated ops (`mailboxList`, `mailboxGet`, `mailboxSync`, `mailboxUpdate`, `mailboxDelete`, `mailboxConnectToken`) unwrapped (neither SDK wraps them). | n/a | P3 | |

---

## 8. Profiles

| Port | # | Item | Details | Python reference | Priority | Decision |
|---|---|------|---------|------------------|----------|----------|
| ❌  | 8.1 | Profiles client | 7 generated ops, zero wrappers: `profileCreate`, `profileGet`, `profileDelete`, `profileList`, `profileDuplicate`, `profileCookiesGet`, `profileCookiesSet`. Only the `profile` field on session start is usable. Python deprecates `generate_cookies` in favor of profiles, so this is the recommended login-persistence path. | `client.profiles.create(name)`, `get(id)`, `delete(id)`, `list(page, page_size, name)` | P1 | |
| ❌  | 8.2 | Profile-level cookie get / set | `profileCookiesGet`, `profileCookiesSet` unwrapped (neither SDK wraps them). | n/a | P3 | |

---

## 9. Managed auth

| Port | # | Item | Details | Python reference | Priority | Decision |
|---|---|------|---------|------------------|----------|----------|
|  ❌ | 9.1 | `checkConnection(connectionId)` | Not present. | `client.managed_auth.check_connection(connection_id)` | P2 | |
|  ❌ | 9.2 | Connect-link flow | 7 generated ops unwrapped: `managedAuthConnectLinkCreate`, `connectLinkContext`, `connectLinkMailboxes`, `connectLinkMailboxConnect`, `connectLinkMailboxSync`, `connectLinkSubmit`, `connectLinkStatus` (neither SDK wraps them). | n/a | P3 | |

---

## 10. File storage

| Port | # | Item | Details | Python reference | Priority | Decision |
|---|---|------|---------|------------------|----------|----------|
| ✅ | 10.1 | Storage object attached to a session | Node exposes `notte.Files(sessionId)` only. No way to attach storage before start so agents can consume uploaded files. | `RemoteFileStorage`, `Session(storage=...)`, `storage.for_session(id)` | P1 | |
| ✅| 10.2 | `metadata(fileId)` | Not present. | `FileStorageClient.metadata(session_id, file_id)` | P2 | |
| ✅  | 10.3 | Download to path with `force` overwrite | Node returns a `Blob`. | `download(file_id, local_dir, force=False)` writes atomically, raises `FileExistsError` unless forced | P2 | |
| ✅ | 10.4 | Upload from path | Node takes a `Blob`. | `upload(file_path, upload_file_name)` | P2 | |
| ❌  | 10.5 | `NOTTE_CACHE_DIR` | n/a | Python honors `NOTTE_CACHE_DIR` for upload/download dirs | P3 | |

---

## 11. Top-level endpoints neither SDK wraps (Node has generated ops)

| Port | # | Item | Generated op | Priority | Decision |
|---|---|------|--------------|----------|----------|
| ✅  | 11.1 | Web search | `searchWeb` (`POST /search`) | P3 | |
| ❌  | 11.2 | Scrape from HTML | `scrapeFromHtml` (`POST /scrape_from_html`) | P3 | |
| ✅  | 11.3 | Anything API | `anythingStart` (`POST /anything/start`) | P3 | |
| ✅  | 11.4 | Secrets store | `listSecrets`, `storeSecret`, `getSecret`, `deleteSecret` | P3 | |
| ✅  | 11.5 | Usage and billing | `getUsage`, `getUsageLogs` | P3 | |
| ❌  | 11.6 | Proxy gateway credentials | `mintProxyCredentials` | P3 | |
| ❌  | 11.7 | Prompt helpers | `improvePrompt`, `nudgePrompt` | P3 | |

---

## 12. Docs, examples and packaging

| Port | # | Item | Details | Priority | Decision |
|---|---|------|---------|----------|----------|
| ✅  | 12.1 | Examples import the wrong package name | `examples/agent.ts`, `persona.ts`, `vault.ts` import from `@notte/sdk`; the package is `notte-sdk`. | P1 | |
| ✅  | 12.2 | README documents non-existent API | `agent.run(task, onUpdate)` positional form, `agent.getId()`, `Session({ timeoutMinutes })`, types `SessionStatus`, `CredentialsDict`, `CreditCardDict`, `CreatePhoneNumberOptions`. Real names are `AgentRunRequest.updateHandler`, `agentId` getter, `idle_timeout_minutes` / `max_duration_minutes`, `CredentialsDictInput`, `CreditCardDictInput`. | P1 | |
| ❌  | 12.3 | Credit card field name mismatch | `examples/vault.ts` uses `card_full_expiration`; README uses `expiry_month` / `expiry_year`. | P2 | remove all credit card fields from the documentation and SDK operations |
| ✅  | 12.4 | Hardcoded persona UUID in example | `examples/persona.ts:104,155` | P2 | |
| ✅  | 12.5 | Types not re-exported from `index.ts` | `FunctionRunListOptions`, `PersonaResponseWithInternalEmail`, `processScrapeResponse`, `prepareAgentRequest`, `parseAgentStatusMessage`. | P2 | |
| ✅  | 12.6 | TypeScript docs snippet coverage | Of 507 snippet files: browser-controls 32 Python / 0 TS, sessions 13 / 0, functions 24 / 1, file-storage 10 / 0, agents 19 / 5, guides 9 / 0, getting-started 7 / 0, personas 2 / 0, vaults 2 / 0. Only scraping (23 / 19) and quickstart (4 / 4) are near parity. | P1 | |
| ✅ | 12.7 | Integration suite not green | `test/INTEGRATION_BACKLOG.md`: 124 passed, 4 failed, 6 skipped. Open fixture work for personas, phone numbers, functions, replay, vault URLs and catch-all assertions. | P1 | |

---

## 13. Node-only features (no Python equivalent, keep)

| Port | # | Item | Details |
|---|---|------|---------|
|✅   | 13.1 | Next.js and generic proxy subpaths | `notte-sdk/next` and `notte-sdk/proxy` with fail-closed auth, path allowlist and SSE passthrough. |
|✅   | 13.2 | Zod-based structured output | `z.toJSONSchema` on the way out and `.parse()` on the way back for scrape and agent answers. |
| ✅  | 13.3 | Manual 307/308 redirect replay and `text/plain` to JSON normalization | Works around undici and Lambda function URL behavior. |
| ✅  | 13.4 | Per-client-instance configuration isolation | Each `NotteClient` owns its own generated client. |
