# Changelog

## Unreleased — interaction renderer functions

Replaced `InteractionOnlyDomNodeRenderingPipe` with functions in `notte_browser.rendering.interaction_only`:
`forward` becomes `render_interactions`, `format` becomes `format_node`, and `render_node` and
`children_texts` keep their names. The attribute constant is now `INCLUDE_ATTRIBUTES`.
Rendering output is unchanged; callers importing the class must use the module functions.

## Unreleased — removed prompt APIs

Removed the agent-only action helpers `non_agent_fields`, `model_dump_agent`,
and `model_dump_agent_json`, and the unused `ActionParameterValue` export.
Regular action serialization, IDs, and descriptions are unchanged.

## Unreleased — retired core errors

Nine unused core error classes and `notte_core.errors.validation` are removed.
Serialized errors naming these retired classes now rehydrate as `NotteBaseError`,
preserving all messages and retry/notify flags but losing the retired subtype identity.
Active error subtypes still rehydrate to their own classes.

## Unreleased — core configuration cleanup

Removed the unused core cache diagnostics (`get_cache_info`, `get_legacy_cache_locations`,
`check_for_legacy_data`), telemetry compatibility attributes (`TELEMETRY_DIR`, `USER_ID_PATH`,
`VERSION_DOWNLOAD_PATH`), and `BaseTelemetryEvent`. Global config fields `level`,
`max_error_length`, and `solve_captchas` are removed; old TOML keys still warn and are skipped.
Session-request `solve_captchas`, cache paths, and PostHog/Scarf delivery are unchanged.

## Unreleased — v2 public resource names

Generated resource methods follow the Node SDK names (snake_case in Python).
No deprecated aliases are provided. Stateful convenience methods are unchanged.

- `client.vaults.add_or_update_credentials` → `client.vaults.credentials_add`
- `client.vaults.get_credentials` → `client.vaults.credentials_get`
- `client.vaults.delete_credentials` → `client.vaults.credentials_delete`
- `client.vaults.list_credentials` → `client.vaults.credentials_list`
- `client.vaults.delete_credit_card` → `client.vaults.credit_card_delete`
- `client.vaults.get_credit_card` → `client.vaults.credit_card_get`
- `client.vaults.set_credit_card` → `client.vaults.credit_card_set`

- `client.personas.list_emails` → `client.personas.emails_list`
- `client.personas.list_sms` → `client.personas.sms_list`

- `client.functions.get` → `client.functions.download_url`
- `client.functions.get_run` → `client.functions.run_get_metadata`
- `client.functions.update_run` → `client.functions.run_update_metadata`
- `client.functions.stop_run` → `client.functions.run_stop`

- `client.sessions.auth_status` → `client.sessions.auth_readiness`

Cleanup completes shared-table coverage and renames `client.functions.run` to `run_start` (stateful `NotteFunction.run` is unchanged). It also exposes the existing Node resource methods for payments, profile cookies/duplication, session profile save/preview/script, function metadata/rollback/schedules/runtime health/payload downloads, and vault update. Page operations remain on Python PageClient; file transfers and function execution retain their handwritten IO implementations.
