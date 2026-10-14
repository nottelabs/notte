# Changelog

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
