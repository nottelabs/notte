# Test Documentation

## Running Tests

### Unit Tests
Run unit tests (no API key required):
```bash
npm run test:unit -- --run
```

### Integration Tests
The function streaming transport suite uses a local HTTP server and needs no credentials:

```bash
npx vitest run test/function-stream.integration.test.ts
```

It covers live log delivery before completion, redirects, split UTF-8/SSE frames,
non-streaming JSON responses, run deadlines (`timeoutMs`), the create-then-execute
request sequence and its headers, the runtime's authentication envelope, failed
executions, malformed/truncated streams, and HTTP errors.

The function live suites own their fixtures: each deploys a browser-free echo
function from a temporary `.py` file through `client.NotteFunction({ path })`
and deletes it in `afterAll`, so no `NOTTE_FUNCTION_ID` is needed.
`function.integration.test.ts` mirrors the Python `test_workflows.py` /
`test_workflow_runs.py` lifecycle (create, get, list, update, download, runs,
delete) and `function-create-run.integration.test.ts` mirrors `test_functions.py`:
`createRun()`, executing the returned ID, and both `getRun()` and the compatible
`retrieve()` alias with streaming enabled and disabled:

```bash
NOTTE_API_KEY=your_api_key npx vitest run test/function.integration.test.ts
NOTTE_API_KEY=your_api_key npx vitest run test/function-create-run.integration.test.ts
```

Run the full integration suite against staging:

```bash
NOTTE_API_URL=https://us-staging.notte.cc NOTTE_API_KEY=your_api_key npm run test:integration
```

CI runs all SDK integration suites on same-repository PRs touching `node-sdk/`,
and on main. Fork PRs run credential-free tests only. Live suites run serially
to respect staging quotas. This migration intentionally preserves existing tests
and their failures. Some legacy tests still require `NOTTE_PERSONA_ID` or
`NOTTE_SESSION_ID`; missing fixtures and stale SDK assumptions
are tracked in [the integration backlog](INTEGRATION_BACKLOG.md), not hidden by
new passing assertions. The account needs session, function, vault, persona, and
agent permissions with sufficient quotas.

The separate paired-documentation workflow enables `docs-snippets.integration.test.ts`
with `NOTTE_DOCS_LIVE=1`; it requires the Python documentation test environment.
That opt-in suite is not executed by the SDK-only job.

Set `NOTTE_API_URL=https://us-staging.notte.cc` explicitly for local runs to avoid
the client's production default. Individual live files should use the integration
command (for its API timeouts), for example `npm run test:integration -- session`.

Run integration tests (requires API key):
```bash
NOTTE_API_KEY=your_api_key npm test session.integration.test.ts
```

Or set the environment variable:
```bash
export NOTTE_API_KEY=your_api_key
npm test session.integration.test.ts
```

## Test Structure

- `session.test.ts` - Unit tests for Session class (mocked, fast)
- `session.integration.test.ts` - Integration tests with real API calls
- Other test files follow the same pattern

## Integration Test Requirements

Integration tests require:
- `NOTTE_API_KEY` environment variable
- Optional: `NOTTE_API_URL` (defaults to https://api.notte.cc)

## Test Coverage

The integration tests cover:
- Basic session start/stop operations
- Context manager pattern (`use()` method)
- Cookie management (set/get cookies, from file)
- Page operations (execute actions, observe)
- Action validation
- Error handling
- Browser type support
- Async iterator pattern

These tests are 1:1 mappings of the Python SDK tests to ensure API compatibility.
