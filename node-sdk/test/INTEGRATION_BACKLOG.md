# Integration follow-up

All integration files own their fixtures and run against staging with
`VITEST_INTEGRATION=1` (see `README.md` in this directory).

Resolved in the Python-parity pass:

- Function tests create and delete their own function instead of relying on
  `NOTTE_FUNCTION_ID`.
- Replays can be requested after `stop()`; `replay()` polls until the recording
  is finalized and the assertions match the current response contract.
- Vault credential URLs are compared as root domains, not absolute URLs.
- Credit card and phone number coverage was removed with the features.

Still open:

- Upstream OpenAPI descriptions should use language-neutral JSON Schema guidance
  and describe `ListPersonasData` filters as personas, not sessions. The Node
  reference currently corrects these descriptions at generation time.

- Existing-persona tests still need an initialized, owned persona fixture
  instead of `NOTTE_PERSONA_ID`. Read the ID only after initialization completes.
- Email/SMS tests assume populated shared inboxes. Keep no-phone coverage
  distinct from success-path SMS coverage.
- Audit inherited catch-all assertions so unexpected backend failures cannot
  count as passing tests.
