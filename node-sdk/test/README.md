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
non-streaming JSON responses, failed executions, malformed/truncated streams, and HTTP errors.

The create-run live suite deploys its own browser-free echo function and cleans it up.
It verifies `createRun()`, executing the returned ID, and both `getRun()` and the
compatible `retrieve()` alias with streaming enabled and disabled:

```bash
NOTTE_API_KEY=your_api_key npx vitest run test/function-create-run.integration.test.ts
```

Live function fixture tests require `NOTTE_API_KEY` and `NOTTE_FUNCTION_ID`
(a function accepting a `url` argument):

```bash
npx vitest run test/function.integration.test.ts
```

The fixture suite is skipped when `NOTTE_FUNCTION_ID` is absent. Existing-persona
tests additionally require `NOTTE_PERSONA_ID`; replay tests require `NOTTE_SESSION_ID`.
Use dedicated test resources. CI only runs the isolated create-run live suite,
not these fixture-dependent suites. Set `NOTTE_API_URL=https://us-staging.notte.cc`
explicitly to avoid the client's production default.

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
