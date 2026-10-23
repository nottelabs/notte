# Changelog

## Unreleased: disabled controls in observations

Observations describe disabled controls instead of dropping them: a disabled input, select, textarea or
button, a control inside a disabled `<fieldset>`, and a link or widget with `aria-disabled="true"`. Each
is rendered in the action space description without an action id and with a `disabled` attribute, e.g.
`_[:]<input type="text" disabled></input>` or `_[:]<button disabled>Submit</button>` (a disabled button
used to appear as its text only, a disabled field not at all). They offer no action, and their nodes have
the new `DomNode.disabled` set, with their live state and accessible name. Controls inside a disabled
`<fieldset>` are no longer offered as actions. Ids and descriptions of enabled elements are unchanged.

## Unreleased: sessions stopped when `with` entry fails

`with client.Session(...) as session:` now stops the session when entering the block fails after
the session was created, for example on an invalid `cookie_file`, a failed cookie upload or a
`KeyboardInterrupt`. The session is stopped with `close_reason="error"` and the original exception
is raised. Before, `__exit__` never ran in that case and the browser kept running until its idle
timeout.

## Unreleased: unexpected JSON responses raise `NotteAPIError`

When a successful API response is not the JSON object or list a method expects (for example
`null`, a number, or a page object without a list of `items`), the sync and async clients raise
`NotteAPIError` with the response's status code and body, instead of an `AttributeError` or
`TypeError`.

## Unreleased: AsyncNotteClient (preview)

`from notte_sdk import AsyncNotteClient` is an asyncio client on `httpx.AsyncClient`, with the
same constructor arguments as `NotteClient`. Its `sessions`, `functions`, `files`, `personas`,
`profiles` and `vaults` resources have the API methods of the sync resources as coroutines, with
the same names, arguments, results, retries and exceptions. Use `async with AsyncNotteClient() as
client:` or `await client.aclose()`: an unclosed client emits a `ResourceWarning` when it is
garbage collected. A client's connections belong to the event loop that opened them; using it
from another open loop raises `RuntimeError`. Preview: not yet available are the methods the sync
resources extend beyond the API call (`sessions.stop`, `set_cookies`, `replay`, `debug_tab_info`,
`page` and the viewers; `functions.run_start`, `update`, `create_run`, `get_curl`,
`run_get_metadata`, `run_update_metadata`; `files.upload`, `download`, `metadata`), `scrape`, and
the `Session`, `Function` and `FileStorage` objects.

`AsyncNotteClient` also has `personas.create_number` and `delete_number`, `vaults.get`,
`managed_auth`, `health_check()`, and the `Persona` and `Vault` objects (`AsyncNottePersona`,
`AsyncNotteVault`). Their methods that call the API are coroutines with the same names and
arguments as the sync versions, and send the same requests. Methods without I/O, such as
`generate_password()` and the vault's redaction helpers, stay plain methods. Create or load an object with
`persona = await client.Persona(...)`, or use `async with client.Persona(...) as persona:` to also
delete it on exit. Credentials go through the same vault code as `NotteVault`, so values read from
the vault are masked the same way. `AsyncNottePersona` implements `aemails`, `asms`,
`await_emails` and `await_sms`, and `AsyncNotteVault` implements the `*_async` vault methods, with
async requests, so a local session can use them without blocking its event loop.

## Unreleased: httpx transport

The Python SDK sends HTTP with httpx instead of requests: one pooled connection set per
`NotteClient`, closed by the new `NotteClient.close()`, by `with NotteClient() as client:`, or
when the client is garbage collected. Retries, timeouts, redirects, proxy and CA environment
variables, and request encoding are unchanged. Transport failures are raised as the new
`notte_sdk.errors.NotteRequestError` subclasses (`NotteConnectionError`, `NotteReadTimeoutError`,
`NotteHTTPStatusError` and others), which also subclass the matching `requests` exceptions, so
existing `except requests.RequestException` handlers keep working; catching the `requests`
classes is deprecated. `NotteHTTPStatusError.response` is an `httpx.Response`. Differences: the
default `User-Agent` is `python-httpx/<version>`, multipart file parts carry a content type, and
a timeout while reading a response body is a `Timeout` rather than a `ConnectionError`.

## Unreleased: generated page, function and session-file methods

The Python SDK now generates every operation in `openapi/resources.json` under the Node SDK's
names, in snake_case. New methods: `client.sessions.scrape`, `observe` and `execute` (the plain
API calls, returning the same core types as `client.sessions.page`), and the session-file aliases
`client.sessions.upload_session_file`, `download_session_file` (returns the file's bytes),
`list_session_files`, `delete_session_file` and `execute_session_file`. `client.functions.create`
is generated with the same arguments and result; it no longer sends the local file path as an
extra form field. Existing methods, including `client.sessions.page`, `client.files` and
`client.functions.run_start`, behave as before.

## Unreleased — accessible names in observations

Observations give each interactive element its accessible name, the name a screen reader announces:
`aria-labelledby`, `<label for>` or a wrapping `<label>`, `aria-label`, `alt`, `<legend>`, a button's
`value` or text, then `title` and `placeholder`, in shadow roots and iframes too. It matches Chromium's
accessibility tree, except that the value of a text field or select is never part of a name, so a name
cannot contain what was typed. It is available as `DomNode.accessible_name` and as the new optional
`accessible_name` of interaction actions (`None` when the element has no name). Names are cut to 200
characters. `text_label`, action ids and descriptions are unchanged.

## Unreleased — LLM content refusals

`LLMEngine` raises the new `ContentFilterError` (an `LLMProviderError` that names the model) when a
provider refuses a request on content-policy grounds: OpenRouter, OpenAI and Azure content-filter
errors (as 400/403/422, or embedded in a 200 body) and a `content_filter` finish reason with no
content. These were reported as `InvalidAPIKeyError`; 401, and 403 without a content-policy
marker, still are. `LLMEngine(timeout=...)` sets the per-attempt HTTP timeout (default 60 s).

## Unreleased — live element state in observations

Observations read the live state of form controls: the current value of inputs, textareas and
contenteditable elements, checked state, `<select>` options, and `aria-expanded` / `aria-selected` /
`aria-pressed`. It is available as `DomNode.state`, `BrowserSnapshot.element_states()` /
`fingerprint()`, and in the new optional `Observation.element_states` (by action id) and
`Observation.fingerprint`. Action ids and descriptions are unchanged. Password fields only report
whether they are filled. Values a session's vault typed are replaced by their placeholders in the
observation's state and fingerprint (`Observation.from_snapshot` now requires the `secrets` to mask),
and card values the vault typed are now part of `BaseVault.get_replacement_map()`.

## Unreleased — deprecated observe options

`observe(instructions=...)` and `perception_type="deep"` are deprecated and will be
removed from the API on December 1, 2026. Passing either to `observe()` (on a
`RemoteSession` or `client.sessions.page`), including a session created with
`perception_type="deep"`, emits a `DeprecationWarning`; requests are unchanged.
Use `perception_type="fast"` (the default) instead of `"deep"`. For `instructions`:
`<<ALTERNATIVE FOR instructions: session.act() — pending>>`. Migration guide: https://docs.notte.cc/features/sessions/observe-migration

## Unreleased — deprecated 1.x aliases

Restored surviving core import paths and matching resource method names as lazy,
warning-once runtime aliases. `workflows` / `Workflow` forward to functions;
`NotteFunction.run(local=False)` ignores the retired keyword, while `local=True`
raises a migration error. No generated code or package structure changes.

## Unreleased — unused browser and core helpers

Removed unused Python helpers: `PlaywrightManager.set_playwright`, `FormFiller.get_found_fields`,
`NotteSession.start_from`, `NotteSession.execute_saved_actions`, `resolve_domain_to_url`,
`TimedSpan.as_fields`, `BrowserSnapshot.compare_with`, `SpaceCategory.is_data`, and
`ActionSpace.interaction_markdown`, `is_empty`, and `sample`. Callers of these methods must migrate;
select actions from `ActionSpace.actions` explicitly instead of using `sample`.

## Unreleased — removed prompt APIs

Removed credential prompt helpers inherited by `NotteVault` (`instructions` and
`system_instructions`), `CredentialField.instructions` / `default_instructions`,
and the unused `instruction_name` / `exposed` metadata. Credential substitution,
validation, serialization, and masking are unchanged.

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

## Unreleased (1.10) — public resource names

Generated resource methods follow the Node SDK names (snake_case in Python).
Deprecated runtime aliases are provided until notte 2.0 (see below). Stateful convenience methods retain their 1.10 behavior.

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

### Migrating from 1.x

These aliases emit one `DeprecationWarning` per old module/method/attribute per
process, naming the replacement and removal in notte 2.0. Enable them with
`python -W default::DeprecationWarning script.py`, then update imports and calls.
They are runtime-only: type checkers should use the 1.10 names. The implementation
is isolated in `notte_core/_v1_aliases.py` and `notte_sdk/_v1_aliases.py`, each
activated by one normal import at the end of its package initializer. Removing
support in 2.0 means deleting those two files and those two import lines.
The existing SDK `_compat/` package and generated code are unchanged.

Core module aliases (prefix every entry with `notte_core.`):

| Old path | Replacement |
|---|---|
| `errors.actions` | `errors` |
| `errors.base` | `errors` |
| `errors.llm` | `errors` |
| `errors.processing` | `errors` |
| `errors.provider` | `errors` |
| `common` | `resource` |
| `common.config` | `config` |
| `common.logging` | `logging` |
| `common.cache` | `cache` |
| `common.resource` | `resource` |
| `common.telemetry` | `telemetry` |
| `common.types` | `schema` |
| `browser.observation` | `observation` |
| `browser.dom_tree` | `dom_tree` |
| `browser.highlighter` | `highlighter` |
| `browser.node_type` | `node_type` |
| `browser.snapshot` | `snapshot` |
| `data.fetch` | `fetch` |
| `data.space` | `data` |
| `ast` | `types` |
| `utils.files` | `config` |
| `utils.image` | `observation` |
| `utils.pydantic_schema` | `schema` |
| `utils.raw_file` | `raw_file` |
| `utils.singleton` | `resource` |
| `utils.url` | `url` |

Only surviving names are available; removed names still raise `ImportError`.
Standard-library modules accidentally re-exported in 1.9.7 remain available
at these paths (including `common.config.os`); prefer direct stdlib imports.
`notte_core.errors` and `notte_core.data` remain real modules.

SDK resource aliases (arguments and results are forwarded unchanged):

| Resource | Old → replacement |
|---|---|
| `vaults` | `get_credentials` → `credentials_get`; `list_credentials` → `credentials_list`; `add_or_update_credentials` → `credentials_add`; `delete_credentials` → `credentials_delete` |
| `vaults` | `get_credit_card` → `credit_card_get`; `set_credit_card` → `credit_card_set`; `delete_credit_card` → `credit_card_delete` |
| `personas` | `list_emails` → `emails_list`; `list_sms` → `sms_list` |
| `functions` (also `workflows`) | `get` → `download_url`; `get_run` → `run_get_metadata`; `run` → `run_start`; `stop_run` → `run_stop`; `update_run` → `run_update_metadata` |
| `sessions` | `auth_status` → `auth_readiness` |
| `NotteClient` | `workflows` → `functions`; `Workflow` → `Function` |
| `NotteFunction` | `workflow_id` → `function_id` |

`Workflow` translates constructor keywords `workflow_id` → `function_id` and
`workflow_path` → `path`, rejecting conflicting values. It returns a v2
`NotteFunction`; retired workflow behavior is not restored.
`NotteFunction.run(local=False)` is equivalent to omitting `local`, warns once,
and preserves the 1.10 signature for introspection. `local=True` raises before
starting a cloud run. Other removed keywords and old positional signatures
must be migrated explicitly.

Not covered by this layer:

- Agents (`client.Agent`, `client.agents`, `AgentFallback`, `notte_agent`):
  keep scripts on 1.x until their agent loops are replaced.
- Image scraping (`only_images`) and local replay: retain 1.x or implement an
  explicit image extractor/use cloud replay.
- `screenshot_type`: remove the retired option.
- `execute(type="scrape")`: use `session.scrape(...)` and adapt the result.
- `perception_type` on the local constructor: move the option to observe/execute;
  review non-default modes before migration.
- The `only_main_content` default changed to `False`: pass `True` explicitly
  when retaining the 1.x extraction scope.
- LLM model enums: use supported model strings. Uppercase endpoint constants
  are not aliased.
- Legacy `create_run(local=...)`, workflow `update(workflow_path=...)` /
  `download(workflow_path=...)`, removed `run` options (`restricted`,
  `workflow_run_id`, `log_callback`), and old positional call layouts require
  explicit migration. The aliases do not restore local execution.

Paths without surviving purpose-built names are omitted: `agent_types`,
`browser.perception`, `common.notifier`, `errors.validation`, and
`utils.code`, `utils.encryption`, `utils.platform`, `utils.webp_replay`.
The empty `browser`/`utils` namespaces only support their listed child aliases.
