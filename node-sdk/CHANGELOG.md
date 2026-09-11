# Changelog

## Unreleased

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
