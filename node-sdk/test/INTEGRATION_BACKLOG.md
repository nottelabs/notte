# Integration follow-up

The pipeline migration enables discovery/execution of all integration files. It
does not claim that every legacy test passes or has a self-contained fixture.
SDK and test corrections are separate in [PR #966](https://github.com/nottelabs/notte/pull/966),
branched directly from main.

Findings from the first complete local run and fixture experiments:

- Existing-persona tests need initialized, owned persona fixtures instead of
  account-specific IDs. Read the ID only after initialization has completed.
- Email/SMS tests assume populated shared inboxes and a provisioned phone.
  Keep no-phone coverage distinct from success-path SMS coverage. Do not silently
  allocate billable phone numbers to satisfy fixtures.
- Function tests need an owned deploy/delete fixture rather than the optional
  `NOTTE_FUNCTION_ID` gate, which currently skips that file when absent.
- Replay requires a stopped session; `stop()` clears the active ID. Retain a way
  to request replay without marking the stopped session active again.
- Replay assertions must match the current response contract and allow bounded
  time for recording finalization. The attempted `.replay.length` assertion failed.
- Vault credential URLs can be normalized hostnames, not absolute URLs;
  `new URL("github.com")` is not a valid assertion implementation.
- Audit inherited catch-all assertions so unexpected backend failures cannot
  count as passing tests.

Initial exploratory full-suite result with fixture changes: 124 passed, 4 failed,
6 documentation cases skipped because they run in their own workflow. This is
not a green result for the unmodified legacy suite. Fixes and targeted results
belong to the separate fixes PR; rerun the complete suite after those land.
