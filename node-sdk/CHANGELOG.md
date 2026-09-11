# Changelog

## Unreleased

- `session.fetch()` refuses plaintext `http:` targets and redirects by default
  because the request carries the page's cookies; pass `allowInsecure: true`
  to override. Relative URLs resolve against the page.
- Manual 307/308 redirect replay strips `x-notte-api-key` as well as
  `Authorization` on cross-origin targets and refuses insecure destinations
  (loopback excepted).
- A caller's own `AbortSignal` is no longer reported as `NotteTimeoutError`;
  only the SDK deadline is. Composite signals use `AbortSignal.any` when available.
- Captcha actions that time out on every retry rethrow the last `NotteAPIError`
  (408) instead of a generic message.
- Cookie files are updated under a per-path lock so sessions stopped
  concurrently do not overwrite each other's cookies.
- `RemoteFileStorage.download()` without `force` links the temporary file into
  place, so a file created after the existence check is never replaced.
- Vault credential URLs are keyed by the Public Suffix List (`tldts`, ICANN
  section, matching `tldextract` in the Python SDK) instead of a suffix heuristic.
- `agent.isRunning()` keeps its synchronous contract but is deprecated: use
  `hasStarted()` for the local check or the new `isActive()` for the live status.
- `npm test` no longer picks up `*.integration.test.ts`; use `npm run test:integration`.

- **Breaking:** remove credit card storage from vaults (`setCreditCard`,
  `getCreditCard`, `deleteCreditCard`) and every mention of it from the
  documentation and examples.
- **Breaking:** remove the deprecated persona phone number management
  (`createNumber`, `deleteNumber`) from the documentation and examples; the
  methods never existed in this SDK.
- Add a typed error hierarchy (`NotteError`, `NotteAPIError`,
  `NotteAPIExecutionError`, `AuthenticationError`, `InvalidRequestError`,
  `NotteTimeoutError`, `FailedToRunCloudFunctionError`, `ScrapeFailedError`,
  `ActionExecutionError`, ...). Every generated call now rejects with a
  `NotteAPIError` carrying `statusCode`, `path` and the parsed body.
- Add `retry()` mirroring `notte_sdk.errors.retry`, and a per-request
  `timeoutMs` client option (default 60 s) that rejects with `NotteTimeoutError`.
- Check the npm registry once per process when a `NotteClient` is constructed
  and warn when a newer release exists. Disable with
  `NOTTE_SDK_DISABLE_VERSION_CHECK=1`.
- Add `client.sessions.list()`, `client.agents.list()`, `client.vaults.list()`
  and `client.functions.list()`.
- Add `client.healthCheck()`.
- Read the database preview branch from `NOTTE_DB_PREVIEW_BRANCH` (or the
  `dbPreview` option) and send it with every request and websocket handshake.
- Add `client.search()` (`POST /search`), `client.anything.start()`
  (`POST /anything/start`), `client.secrets` (`list`, `store`, `get`, `delete`)
  and `client.usage` (`get`, `logs`).
- Fix the examples to import from `notte-sdk` and read the persona id from
  `NOTTE_PERSONA_ID` instead of a hardcoded UUID.
- Fix the README to document the real `agent.run({ task, updateHandler })`
  form, `agent.agentId`, and the `idle_timeout_minutes` /
  `max_duration_minutes` session options.
- Sessions: typed `execute()` with the `actions` builders (`actions.click({ id })`,
  `actions.goto({ url })`, ...); failed actions throw `ActionExecutionError`
  rehydrated from the API's `exception_detail`; `start()` retries 5xx errors and
  cluster overload like Python; captcha actions get a 100 s timeout and retry on 408.
- Sessions: add `evaluateJs()`, `fetch()` (in-page HTTP requests), `cdpUrl()`,
  `page()` (Playwright over CDP, `playwright-core` is an optional peer dependency),
  `debugInfo()`, `debugTabInfo()`, `getScript()`, the `cookie_file`, `storage`,
  `raiseOnFailure` and `perception_type` options, `replay()` polling until the
  recording is ready (also after `stop()`) and `downloadReplay()`.
- Scraping: `client.scrape()` and `session.scrape()` no longer invent
  `instructions` from the schema; structured extractions throw
  `ScrapeFailedError` on failure and return the extracted data directly, or the
  `StructuredData` wrapper with `raiseOnFailure: false`.
- Functions: create from a local script with `notte.NotteFunction({ path })`,
  `get()`, `update()`, `updateMetadata()`, `delete()`, `setSchedule()`,
  `deleteSchedule()`, `rollback()`; `run()` creates the run then executes it like
  Python, accepts `timeoutMs`, no longer requires a raw API key (proxy mode works),
  and throws `FailedToRunCloudFunctionError` on failed runs.
- Vaults: `getCredentials()` now throws instead of returning `null`; add
  `hasCredential()`; credentials are validated client-side like Python.
- File storage: add `RemoteFileStorage` (`notte.FileStorage()`) with upload from
  path, `metadata()`, `download()` to disk with `force`, `FileExistsError` and
  `FileNotFoundError`; `SessionFiles` now uses the generated file operations.
- Add `NotteFunction.createRun()` to obtain a cloud run ID before execution, and
  `run(variables, { functionRunId })` to execute that record. Add `getRun()`;
  `retrieve()` remains a compatible alias.

- **Breaking:** `NotteFunction.run()` now streams logs and waits for completion
  by default, matching Python. Add `{ stream: false }` as the second argument
  to preserve the previous JSON response without live logs. Standard-runtime
  calls still wait for completion with streaming disabled.
- Streaming calls return a typed `FunctionRunResult`. Calls reject failed executions
  by default. Use `raiseOnFailure: false` to receive the failed response, and
  `onLog` to customize or silence log output.
## Review hardening

- Isolate configuration and credentials per client instance.
- Require caller authentication for server-side proxies (missing callbacks return 401).
- Poll agents to completion after log transport failures, with an explicit timeout.
- Reuse persona initialization and only automatically delete personas owned by the wrapper.
- Isolate legacy client factories and preserve resolved configuration defaults.
- Send session files as multipart data through the generated HTTP client.
- Use session-scoped expiring viewer tokens for agent logs instead of account keys.
