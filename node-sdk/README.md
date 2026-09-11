# notte-sdk

> TypeScript SDK for Notte - Cloud-hosted browser sessions with LLM-powered web agents

The official TypeScript SDK for Notte API, providing cloud-hosted browser sessions with precise control, LLM-powered web agents for automated tasks, serverless functions, and secure credential management.

## Contributing

This directory is a standalone npm package. Node.js 22 and 24 are tested in CI;
Python tooling is not required to build or test it.

```bash
cd node-sdk
npm ci
npm run typecheck
npm run test:unit -- --run
npx vitest run test/function-stream.local.test.ts  # also part of npm run test:unit
npm run build
node scripts/check-package.js
npm pack --dry-run
```

`npm run build` compiles the checked-in client without contacting the API.
To update the generated client, run `npm run generate:staging`, review the diff,
and commit it. `npm run check:staging` checks for drift without editing your files.

For the isolated live test, set `NOTTE_API_KEY` and
`NOTTE_API_URL=https://us-staging.notte.cc`, then run:

```bash
npx vitest run test/function-create-run.integration.test.ts
```

This test creates its own function and deletes it afterward. Other live suites
may require pre-existing fixtures; see [test documentation](test/README.md).
The `node sdk cicd` workflow runs on every PR touching `node-sdk/`:

- `tests` runs unit tests, local HTTP integration tests, type checks, and package
  checks on Node.js 22 and 24, including for fork PRs.
- `integration-tests` runs the isolated live function lifecycle tests against
  staging on same-repository PRs. Fork PRs skip this credentialed job.

Both jobs also run on main pushes and manual workflow runs on main. API drift
checks remain limited to main pushes and manual workflow runs on main.

### Releases

The npm package remains `notte-sdk`. Its MIT license is in [LICENSE](LICENSE);
the repository root license does not replace this package's license.

The Node SDK is released together with the Python SDK, from the same tag and at
the same version. Cutting a release means creating a GitHub release tagged
`vX.Y.Z` on [nottelabs/notte](https://github.com/nottelabs/notte/releases):

- `pypi-release.yml` publishes the Python packages to PyPI as `X.Y.Z`.
- `node-sdk-publish.yml` sets this package's version to `X.Y.Z`, runs the
  typecheck, unit tests, streaming test and export smoke test, publishes to npm
  with provenance, then installs the published version back from npm to verify it.

`package.json` stays at `0.0.0-dev` on `main`; the version is only set in CI
from the tag, like the `.dev` placeholder in the Python `pyproject.toml` files.
Publishing uses npm trusted publishing (GitHub OIDC) bound to this repository,
workflow `node-sdk-publish.yml` and environment `npm`, so no npm token is stored
in the repository. To dry-run a release build locally, run `make release X.Y.Z`
in this directory; it never publishes.

Importing the SDK does not contact the npm registry. Constructing a `NotteClient`
performs a one-time, non-blocking check per process and warns when a newer
release exists, like the Python SDK. Set `NOTTE_SDK_DISABLE_VERSION_CHECK=1` to
disable it. To explicitly check for an update, call `await checkForLatestVersion()`
from `notte-sdk`.
API URLs must use HTTPS, except HTTP loopback addresses for local development.

## Features

### Server-side proxy security

`createNotteProxy` from `notte-sdk/next` requires an `authenticate` callback at
runtime. Without one, requests return 401 even when a server API key is configured.
The callback must verify caller identity and authorize access to requested
resources. Returning a user-specific Notte API key isolates accounts; returning
void uses the shared server key and requires application-level ownership checks.
An endpoint allowlist is not a substitute for authorization. Relative HTTP proxy
clients poll agent status for completion because they cannot use backend WebSockets.

- 🌐 **Cloud Browser Sessions** - Access remote browsers with full control
- 🤖 **LLM-Powered Agents** - Intelligent web automation with natural language
- 🔒 **Secret Vaults** - Enterprise-grade credential management with end-to-end encryption
- 👤 **Digital Personas** - Complete identities with email, SMS, and 2FA for automated account creation
- 🎯 **Session Management** - Context managers for reliable resource cleanup
- 📡 **Real-time Updates** - WebSocket support for live agent monitoring
- 📝 **Type Safety** - Full TypeScript support with generated types
- ⚡ **Serverless Functions** - Run pre-built automation workflows with simple API calls
- 🔍 **Web Search, Secrets and Usage** - Search the web, manage workspace secrets and read billing usage
- 🔄 **Auto-sync** - Generated from OpenAPI spec, always up-to-date

## Installation

```bash
npm install notte-sdk
```

## Quick Start

### Basic Session Usage

```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient({
  apiKey: 'your-api-key', // pragma: allowlist secret
  baseUrl: 'https://api.notte.cc' // optional, defaults to https://api.notte.cc
});

// Use session with automatic cleanup (mirrors Python's context manager)
await notte.Session({ idle_timeout_minutes: 5 }).use(async (session) => {
  const status = await session.status();
  console.log('Session status:', status);
});
```

### Agent Automation

```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient();

// Run an agent task with live updates
await notte.Session().use(async (session) => {
  const agent = notte.Agent({ session, max_steps: 10 });

  const response = await agent.run({
    task: "Find the best Italian restaurant in San Francisco and book a table for 2 at 7pm today",
    updateHandler: (update) => {
      // Receive real-time updates via WebSocket
      console.log(`[${update.type}]`, update.data);
    }
  });

  console.log(`Agent completed: ${response.success ? 'Success' : 'Failed'}`);
  console.log(`Answer: ${response.answer}`);
});
```

## Core Classes

### NotteClient

The main client for interacting with the Notte API.

```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY, // defaults to NOTTE_API_KEY
  baseUrl: 'https://api.notte.cc',   // defaults to NOTTE_API_URL or https://api.notte.cc
  timeoutMs: 60_000,                 // per-request timeout, default 60 s
  verbose: false,                    // log every request
});

// Create sessions
const session = notte.Session({ idle_timeout_minutes: 5, max_duration_minutes: 30 });

// Create agents
const agent = notte.Agent({ session, max_steps: 15 });

// Create vaults
const vault = notte.Vault({ name: 'My Vault' });

// Create personas
const persona = notte.Persona({ create_vault: true });

// Check that the API is reachable (rejects with NotteAPIError otherwise)
await notte.healthCheck();
```

#### Listing resources

Every resource has a `list()` namespace, mirroring `client.sessions.list()` and
friends in Python. Options are the generated query parameters of the matching
endpoint (`SessionListOptions`, `AgentListOptions`, `VaultListOptions`,
`FunctionListOptions`, `PersonaListOptions`).

```typescript
const sessions = await notte.sessions.list({ only_active: true });
const agents = await notte.agents.list({ page_size: 10 });
const vaults = await notte.vaults.list();
const functions = await notte.functions.list();
const personas = await notte.personas.list({ only_active: true });
```

#### Database preview branches

Set `NOTTE_DB_PREVIEW_BRANCH` (or pass `dbPreview` to the client) to route every
request and websocket handshake to a database preview branch. This is an internal
option used when testing API changes.

### Session

Manages browser sessions with automatic lifecycle management.

```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient();

// Context manager pattern (automatic start/stop)
await notte.Session({ idle_timeout_minutes: 5 }).use(async (session) => {
  // Session is automatically started
  console.log('Session ID:', session.getId());

  const status = await session.status();
  console.log('Session status:', status);

  // Session is automatically stopped when done
});

// Manual session management
const session = notte.Session({ open_viewer: true });
await session.start();
try {
  const status = await session.status();
  console.log('Session status:', status);
} finally {
  await session.stop();
}

// Async iterator pattern
for await (const session of notte.Session({ max_duration_minutes: 15 })) {
  // Use session here
  const status = await session.status();
  console.log('Session active:', status);
  // Session automatically closed after loop
}
```

#### Browser control

Drive the page with typed actions, exactly like `session.execute(...)` in Python.
Element ids (`B1`, `I2`, ...) must come from a live `observe()` call.

```typescript
import { NotteClient, actions, ActionExecutionError } from 'notte-sdk';

const notte = new NotteClient();

await notte.Session().use(async (session) => {
  await session.execute(actions.goto({ url: 'https://www.notte.cc' }));

  const observation = await session.observe({ perception_type: 'deep' });
  console.log(observation.space);

  // Plain objects work too; the `type` field is a discriminated union
  await session.execute({ type: 'click', id: 'B1' });
  await session.execute(actions.fill({ selector: 'internal:text="Email"', value: 'me@example.com' }));

  // A failed action throws ActionExecutionError with the server-side error type
  try {
    await session.execute(actions.click({ id: 'B999' }));
  } catch (error) {
    if (error instanceof ActionExecutionError) console.log(error.errorType, error.userMessage);
  }

  // Or inspect the result yourself
  const result = await session.execute(actions.click({ id: 'B999' }), { raiseOnFailure: false });
  console.log(result.success, result.message);

  // Run JavaScript in the page and fetch through the page (cookies, proxy, fingerprint).
  // Relative URLs resolve against the page; plaintext http targets are refused unless allowInsecure is set.
  const title = await session.evaluateJs('document.title');
  const summary = await session.fetch('/api/rest_v1/page/summary/Main_Page').then(r => r.json());

  // Scrape the current page
  const markdown = await session.scrape({ only_main_content: true });

  // Cookies
  const cookies = await session.getCookies();
  await session.setCookies(cookies);
});
```

#### Playwright access

`playwright-core` is an optional peer dependency (`npm install playwright-core`),
the counterpart of `pip install notte-sdk[playwright]`:

```typescript
await notte.Session().use(async (session) => {
  const page = await session.page(); // connected over CDP, cached
  await page.goto('https://www.notte.cc');
  await page.screenshot({ path: 'screenshot.png' });

  // Or connect your own tooling
  const cdpUrl = await session.cdpUrl();
});
```

#### Replays and cookie files

```typescript
// Persist login state between runs: loaded on start, appended on stop
const session = notte.Session({ cookie_file: './cookies.json' });

await session.use(async () => { /* ... */ });

// Replays are generated after stop(); replay() polls until ready (240 s by default)
const replay = await session.replay();
await session.downloadReplay('./session.mp4');
```

#### Session Methods

- `start()` - Start the session (retries 5xx errors 3 times, waits 30 s on cluster overload)
- `stop(closeReason?)` - Stop the session
- `status()` - Get session status
- `use(callback)` - Context manager pattern
- `getId()` - Get session ID
- `isSessionActive()` - Check if session is running
- `execute(action, options?)` - Execute a typed action; throws `ActionExecutionError` on failure unless `raiseOnFailure: false`
- `observe(options?)` - Observe the page (`perception_type`, `min_nb_actions`, `max_nb_actions`)
- `scrape(options?)` - Scrape the page as markdown, images, or structured data (see [Scraping](#scraping))
- `evaluateJs(code, options?)` - Evaluate JavaScript and return the stringified result
- `fetch(url, options?)` - Issue an HTTP request from inside the page
- `setCookies(cookies)` / `setCookiesFromFile(path)` / `getCookies()` - Manage cookies
- `cdpUrl()` - Chrome DevTools Protocol websocket URL
- `page()` - Playwright `Page` connected over CDP (requires `playwright-core`)
- `debugInfo()` / `debugTabInfo(tabIdx?)` - Debug URLs and tab metadata
- `replay(options?)` / `downloadReplay(path?)` - Session recording
- `getScript(options?)` - Python code reproducing the session
- `viewer()` - Open the live session viewer in the local default browser
- `storage` - The `RemoteFileStorage` attached with the `storage` option
- `client.sessions.list(options?)` - List sessions

### Agent

Executes tasks using LLM-powered web automation.

```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient();

await notte.Session().use(async (session) => {
  const agent = notte.Agent({
    session,
    max_steps: 10
  });

  // Non-blocking: start agent and get its ID
  await agent.start({ task: "Navigate to Google and search for 'TypeScript'" });
  console.log('Agent started:', agent.agentId);

  // Check agent status
  const status = await agent.status();
  console.log('Agent status:', status);

  // Blocking: run agent and wait for completion with live updates
  const response = await agent.run({
    task: "Find the latest TypeScript documentation",
    updateHandler: (update) => {
      if (update.type === 'step') {
        console.log(`Step update:`, update.data);
      } else if (update.type === 'completion') {
        console.log(`Completed:`, update.data);
      }
    }
  });

  console.log('Final result:', response);
});
```

#### Agent Methods

- `start(request)` - Start agent with `{ task, url?, ... }` (non-blocking)
- `run(request)` - Start agent and wait for completion (blocking); pass `updateHandler` for live updates
- `status()` - Get agent status
- `stop()` - Stop the agent
- `agentId` - The agent ID (read-only property, available after `start()` / `run()`)
- `sessionId` - The session ID the agent runs in (read-only property)
- `hasStarted()` - Whether `start()`/`run()` was called on this instance (local check)
- `isActive()` - Whether the agent is still active on the server (fetches the status)
- `isRunning()` - Deprecated alias of `hasStarted()`; it does not contact the API

#### Structured answers with Zod

Both `agent.start()` and `agent.run()` accept a Zod schema as `response_format`.
The SDK converts it to JSON Schema before calling the API. On `run()`, the final
`answer` is validated against the schema and typed accordingly.

```typescript
import { z } from 'zod';

const Answer = z.object({ title: z.string(), summary: z.string() });

await notte.Session().use(async (session) => {
  const agent = notte.Agent({ session, max_steps: 5 });
  const result = await agent.run({
    task: 'Go to notte.cc and return the page title and summary',
    response_format: Answer,
  });
  // result.answer is typed as { title: string; summary: string } and validated
  console.log(result.answer.title);
});
```

### Secret Vaults

Manage credentials securely with enterprise-grade encryption.

```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient();

// Create a new vault
const vault = notte.Vault({ name: 'My Secure Vault' });

// Add credentials for websites
await vault.addCredentials('https://github.com/', {
  email: 'user@example.com',
  password: 'secure-password', // pragma: allowlist secret
  mfa_secret: 'PYNT7I67RFS2EPR5' // pragma: allowlist secret
});

// Generate secure passwords
const strongPassword = vault.generatePassword(20, true); // 20 chars with special chars
const simplePassword = vault.generatePassword(12, false); // 12 chars, no special chars

// Use with agents for automatic credential management
await notte.Session().use(async (session) => {
  const agent = notte.Agent({
    session,
    vault_id: vault.vaultId // Agent will use vault for authentication
  });

  const result = await agent.run({
    task: "Login to GitHub and create a new repository",
    url: "https://github.com/login"
  });
});

// Access existing vault
const existingVault = notte.Vault({ vault_id: 'vault-abc-123' });
const credentials = await existingVault.listCredentials();

// Cleanup
await vault.deleteCredentials('https://github.com/');
await vault.stop(); // Deletes entire vault
```

#### Vault Methods

- `addCredentials(url, credentials)` - Store credentials for a URL (validated client-side like Python: root domain, exactly one of `email`/`username`, base32 `mfa_secret`)
- `addCredentialsFromEnv(url)` - Read `{DOMAIN}_EMAIL` / `{DOMAIN}_USERNAME` / `{DOMAIN}_PASSWORD` / `{DOMAIN}_MFA_SECRET` from the environment
- `getCredentials(url)` - Retrieve credentials for a URL; throws `NotteAPIError` when none exist
- `hasCredential(url)` - Whether credentials exist for a URL
- `deleteCredentials(url)` - Delete credentials for a URL
- `listCredentials()` - List all stored credentials
- `generatePassword(length?, includeSpecialChars?)` - Generate secure passwords
- `delete()` - Delete the entire vault
- `stop()` - Stop and delete the vault
- `client.vaults.list(options?)` - List vaults

#### Security Features

- **End-to-End Encryption** - All credentials encrypted at rest and in transit
- **Zero Trust Architecture** - Credentials never exposed to LLMs or external services
- **Access Control** - Strict access logging and permissions
- **Two-Factor Authentication** - Support for MFA secrets (TOTP)

### Personas

Manage complete digital identities for automated account creation and 2FA.

```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient();

// Create a new persona with a vault
const persona = notte.Persona({ create_vault: true });

// Get persona information (the first call initializes the persona)
const info = await persona.get();
console.log(`Email: ${info.email}`);

// Read emails sent to the persona
const emails = await persona.emails({
  limit: 10,
  only_unread: true
});
console.log(`Received ${emails.length} new emails`);

// Read SMS messages for 2FA codes
const smsMessages = await persona.sms({
  limit: 5,
  only_unread: true
});
console.log(`Received ${smsMessages.length} SMS messages`);

// Use with agents for automated account creation
await notte.Session().use(async (session) => {
  const agent = notte.Agent({
    session,
    vault_id: persona.vault.vaultId // Agent will use persona's vault
  });

  const result = await agent.run({
    task: `Create an account on GitHub using the persona credentials`
  });
  console.log(`Account created: ${result.success}`);
});

// Access existing persona
const existingPersona = notte.Persona({ persona_id: 'persona-abc-123' });
const personaEmails = await existingPersona.emails();

// Add credentials to persona's vault
await persona.addCredentials('https://github.com/');
// This automatically generates a secure password and stores:
// - Email: persona's email
// - Password: generated secure password

// Cleanup
await persona.stop(); // Deletes persona and all associated data
```

#### Persona Methods

- `get()` - Fetch (and initialize) the persona information
- `emails(options?)` - Read emails sent to the persona
- `sms(options?)` - Read SMS messages sent to the persona
- `addCredentials(url)` - Add auto-generated credentials to the persona's vault
- `delete()` - Delete the persona
- `stop()` - Stop and delete the persona

#### Message Reading Options

```typescript
const options = {
  limit: 10,              // Maximum number of messages (default: unlimited)
  only_unread: true,      // Only return unread messages (default: false)
  timedelta: '1h'         // Maximum age of messages (e.g., '1h', '30m', '24h')
};

const emails = await persona.emails(options);
const sms = await persona.sms(options);
```

#### Persona Features

- **Complete Digital Identity** - Unique email address
- **2FA Support** - Receive and read SMS verification codes automatically
- **Automated Account Creation** - Seamless integration with agents for signup flows
- **Vault Integration** - Optional secure credential storage
- **Email Management** - Full email reading capabilities
- **Message Tracking** - Mark messages as read/unread automatically

### Functions

Run pre-built automation workflows (Notte Functions) with a simple API call. Functions are serverless workflows that run on Notte's infrastructure — you provide the `function_id` and input variables, and get the result back.

```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient();

// Create a function instance
const fn = notte.NotteFunction({
  function_id: 'your-function-id',
  decryption_key: 'optional-decryption-key' // optional, for encrypted outputs
});

// Stream logs to console.log and wait for the final result (default)
const result = await fn.run({
  url: 'https://example.com',
  query: 'extract pricing information'
});

console.log('Run ID:', result.function_run_id);
console.log('Result:', result.result);

// Retrieve the run result / metadata later
const metadata = await fn.getRun(result.function_run_id);
console.log('Status:', metadata.status); // 'active' | 'closed' | 'failed'
console.log('Result:', metadata);
```

#### Selecting the runtime

`run` defaults to the standard Lambda runtime. Where the extended runtime pilot
is enabled, select AgentCore per invocation with the second argument:

```typescript
const result = await fn.run(
  { url: 'https://example.com' },
  { runtime: 'extended' }
);

// The default is equivalent to an explicit standard selection.
await fn.run({ url: 'https://example.com' }, { runtime: 'standard' });
```

The runtime option stays separate from script input variables. Extended requests
fail explicitly if that runtime is unavailable or at capacity; they do not fall
back to Lambda. Browser sessions keep their own duration limits. Existing
schedules continue to use the standard runtime during the pilot.

#### Create a run before execution

`createRun()` is optional: use it when you need a run ID before execution starts.
It only creates the cloud run record. Pass the returned ID as `functionRunId` to
execute that record; omitting `functionRunId` makes `run()` create a new run.

```typescript
const fn = notte.NotteFunction({ function_id: 'your-function-id' });
const { function_run_id } = await fn.createRun();
console.log('Run ID before execution:', function_run_id);

const pending = fn.run(
  { url: 'https://example.com' },
  { functionRunId: function_run_id },
);

// Do other work here, then wait for completion.
const result = await pending;
console.log(result.result);

const metadata = await fn.getRun(function_run_id);
console.log(metadata.status);
```

`getRun()` fetches the current status and stored result without waiting for execution
to finish. `retrieve()` remains a compatible alias. Execution results contain the
function's structured output; the stored `metadata.result` is serialized JSON.

Keeping the promise lets your JavaScript continue while the HTTP request remains
open. Keep the process running until it completes. This is not a detached job.
With `{ stream: false }`, the SDK returns JSON without live logs, but standard
execution still waits for completion.

#### Streaming options and migration

**Breaking change:** `run()` now defaults to `stream: true`, matching the Python SDK.
It consumes the event stream, prints logs as they arrive, and resolves with the
final response, including `status` and `result`. Existing callers that require a
JSON response without live logs must add `{ stream: false }` as the second argument.

Failed executions throw by default. Set `raiseOnFailure: false` to inspect the
failed response yourself. Transport and malformed-stream errors still throw.
Use `onLog` to route logs to your application (or `onLog: () => {}` to silence them):

```typescript
const result = await fn.run({ url: 'https://example.com' }, {
  onLog: message => console.log('[function]', message),
  raiseOnFailure: false,
});
```

Options belong in the second argument; a `stream` field in the first argument
is a script input and does not change streaming behavior.

#### Downloading the function code

```typescript
const fn = notte.NotteFunction({ function_id: 'your-function-id' });

// Get the python source of the function
const code = await fn.download();

// Or write it straight to a file (the path must end with .py)
await fn.download({ path: './my-function.py' });

// A specific version, and the presigned url on its own
const url = await fn.getUrl({ version: 'v1.0.0' });
```

Notte managed functions return an encrypted url. Pass the key on the function, or
per call, and it is decrypted for you:

```typescript
const fn = notte.NotteFunction({
  function_id: 'your-function-id',
  decryption_key: 'your-decryption-key',
});
const code = await fn.download();
```

#### Creating and managing functions

Upload a Python script to create a function, like `NotteFunction(path=...)` in Python.
Creation is lazy: the upload happens on the first call that needs the function id.

```typescript
const fn = notte.NotteFunction({ path: './my_function.py', name: 'price-monitor', description: 'Checks prices' });

const details = await fn.get();                 // metadata, versions and download link
await fn.update({ path: './my_function_v2.py' }); // upload a new version
await fn.updateMetadata({ name: 'price-monitor-v2' });
await fn.rollback({ version: details.latest_version });

await fn.setSchedule({ cron: '0 9 * * *', variables: { url: 'https://example.com' } });
await fn.deleteSchedule();

const runs = await fn.runs();                   // all runs, including completed ones
const functions = await notte.functions.list();

await fn.delete();
```

`run()` waits at most 300 s by default; pass `timeoutMs` to change it. A failed
run throws `FailedToRunCloudFunctionError` unless `raiseOnFailure: false`.

#### Function Methods

- `run(variables?, options?)` - Stream logs and wait for completion; use `stream: false` for the backend's JSON response without live logs. Options: `runtime`, `functionRunId`, `onLog`, `raiseOnFailure`, `timeoutMs`
- `get(options?)` - Function metadata, versions and download link
- `update(options)` / `updateMetadata(body)` - Upload a new version / change name, description
- `delete()` - Delete the function
- `setSchedule(body)` / `deleteSchedule()` - Manage the cron schedule
- `rollback(options)` - Roll back to a previous version
- `runs(options?)` - List runs (all runs by default, `only_active: true` for active ones)
- `createRun()` - Create a cloud run record without executing it
- `getRun(functionRunId)` - Get current metadata/result for a specific run
- `retrieve(functionRunId)` - Compatibility alias for `getRun()`
- `download(options?)` - Download the function code, optionally writing it to `options.path`
- `getUrl(options?)` - Get the (decrypted) download url of the function code
- `getFunctionId()` - Get the function ID
- `functionId` - The function ID (read-only property)
- `decryptionKey` - The decryption key, if provided (read-only property)

### File Storage

Upload files for a session to use and download files the session produced,
the counterpart of `client.FileStorage()` in Python.

```typescript
import { NotteClient, FileExistsError } from 'notte-sdk';

const notte = new NotteClient();
const storage = notte.FileStorage();
let sessionId = '';
let fileId = '';

await notte.Session({ storage }).use(async (session) => {
  sessionId = session.getId()!;

  // Upload from a path, a Blob or a Uint8Array
  const uploaded = await storage.upload('./invoice.pdf');
  fileId = uploaded.id;

  // ... let the session / an agent download something ...

  const downloads = await storage.list({ source: 'session_download' });
  for (const file of downloads.files) {
    const path = await storage.download(file.id, './downloads');
    console.log('saved', path);
  }

  const info = await storage.metadata(uploaded.id);
  await storage.delete(uploaded.id);
});

// Files of a closed session
const files = notte.FileStorage(sessionId);
await files.download(fileId, './downloads', { force: true }); // overwrite instead of FileExistsError
```

`notte.Files(sessionId)` exposes the same operations returning `Blob`s instead of writing to disk.

### Web Search

Search the public web with `POST /search`. The default `outputType` returns
ranked results; `sourcedAnswer` returns a written answer with its sources.

```typescript
const { results } = await notte.search('notte browser automation', { depth: 'fast' });
results.forEach(item => console.log(item.name, item.url));

const { answer, sources } = await notte.search('what is notte?', { outputType: 'sourcedAnswer' });
console.log(answer, sources.map(s => s.url));
```

Extra fields such as `maxResults` or `includeDomains` are forwarded to the search
provider. `SearchOptions` and the `SearchResultsResponse` /
`SearchSourcedAnswerResponse` shapes are exported.

### Anything API

`notte.anything.start({ task })` (`POST /anything/start`) turns a plain-English
description of a web task into a deployed, reusable function. Building is slow and
billable; prefer `notte.functions.list()` when a ready-made function already fits.
The API response is not typed by the OpenAPI spec and is exposed as an opaque
`AnythingStartResponse` record (it references the built function, e.g. `function_id`).

```typescript
const started = await notte.anything.start({ task: 'fetch the top 3 hacker news posts' });
console.log(started);
```

### Secrets

Workspace secrets (`/secrets`) are scoped by namespace: `llm_provider` keys are
used by agents and scraping, `function_env` values are injected into function runs.
Listing never returns values, only metadata with a `key_hint`.

```typescript
const meta = await notte.secrets.store({ namespace: 'function_env', name: 'API_TOKEN', value: 'xyz' });
const { value } = await notte.secrets.get('API_TOKEN', 'function_env');
const secrets = await notte.secrets.list({ namespace: 'function_env' });
await notte.secrets.delete(meta.id);
```

### Usage

Read billing usage for the current (or a given) monthly period, and page through
per-request usage logs.

```typescript
const usage = await notte.usage.get();
console.log(`${usage.session_count} sessions, $${usage.total_cost} this period`);

const page = await notte.usage.logs({ endpoint: 'sessions.start', page: 1, page_size: 50 });
page.items.forEach(log => console.log(log.created_at, log.endpoint, log.duration_ms));
```

## Advanced Usage

### Session Configuration

```typescript
const session = notte.Session({
  idle_timeout_minutes: 5,    // Close the session after this much inactivity
  max_duration_minutes: 45,   // Hard limit on the session lifetime
  // Add other session options as supported by the API (SessionOptions)
});
```

### Agent Configuration

```typescript
const agent = notte.Agent({
  session: session,
  max_steps: 20,             // Maximum steps for agent (default: 10)
});
```

### Error Handling

Every error thrown by the SDK extends `NotteError`, mirroring `notte_sdk.errors`
in Python. Generated API calls reject with a `NotteAPIError` carrying the request
`path`, the HTTP `statusCode` and the parsed response body in `error`; the API can
flag failures as `NotteAPIExecutionError`. Client-side problems use dedicated
classes: `AuthenticationError` (missing key), `InvalidRequestError`,
`NotteTimeoutError` (request or wait deadline exceeded),
`FailedToRunCloudFunctionError`, `ScrapeFailedError` and `ActionExecutionError`.

```typescript
import { NotteAPIError, NotteError, NotteTimeoutError } from 'notte-sdk';

try {
  await notte.Session().use(async (session) => {
    const agent = notte.Agent({ session });
    const response = await agent.run({ task: "Complete a complex task" });

    if (!response.success) {
      console.error('Agent failed:', response.answer);
    }
  });
} catch (error) {
  if (error instanceof NotteAPIError) {
    console.error(`API ${error.statusCode} on ${error.path}:`, error.apiMessage ?? error.error);
  } else if (error instanceof NotteTimeoutError) {
    console.error('Timed out:', error.message);
  } else if (error instanceof NotteError) {
    console.error('SDK error:', error.message);
  } else {
    throw error;
  }
}
```

### Timeouts and retries

The client applies a per-request timeout (`timeoutMs`, default 60 000 ms; `0`
disables it) through response-body consumption and rejects with `NotteTimeoutError`
when it elapses. Explicit streams use the caller's signal for body cancellation;
function runs supply their own execution deadline. `retry()` wraps an async function so it is re-attempted on failure, like the Python
`@retry` decorator:

```typescript
import { NotteClient, retry } from 'notte-sdk';

const notte = new NotteClient({ timeoutMs: 30_000 });

const start = retry(() => notte.Session().start(), {
  maxTries: 3,
  delayMs: 1_000,
  shouldRetry: error => error instanceof NotteTimeoutError,
});
await start();
```

### WebSocket Updates

The `agent.run()` method provides real-time updates via WebSocket through the
`updateHandler` option:

```typescript
const response = await agent.run({
  task: "Your task",
  updateHandler: (update) => {
    switch (update.type) {
      case 'step':
        console.log('Step:', update.data);
        break;
      case 'completion':
        console.log('Task completed:', update.data);
        break;
      default:
        console.log('Update:', update);
    }
  }
});
```

### Legacy API Support

For backward compatibility, you can still use the legacy client creation:

```typescript
import { createClient, client } from 'notte-sdk';

// Legacy method 1
const legacyClient = createClient({
  baseUrl: 'https://api.notte.cc',
  token: 'your-api-key'
});

// Legacy method 2
import { client } from 'notte-sdk';
client.setConfig({ baseUrl: 'https://api.notte.cc' });
client.interceptors.request.use((request) => {
  request.headers.set('Authorization', 'Bearer your-api-key');
  return request;
});
```

## Python SDK Equivalence

This TypeScript SDK closely mirrors the Python SDK patterns:

### Python
```python
from notte_sdk import NotteClient

notte = NotteClient()

# Session context manager
with notte.Session(idle_timeout_minutes=2) as session:
    status = session.status()
    print(status)

# Agent usage
with notte.Session() as session:
    agent = notte.Agent(session=session, max_steps=10)
    response = agent.run(task="Find the best italian restaurant in SF")
    print(f"Agent completed: {response.success}, answer: {response.answer}")
```

### TypeScript
```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient();

// Session context manager equivalent
await notte.Session({ idle_timeout_minutes: 2 }).use(async (session) => {
  const status = await session.status();
  console.log(status);
});

// Agent usage
await notte.Session().use(async (session) => {
  const agent = notte.Agent({ session, max_steps: 10 });
  const response = await agent.run({ task: "Find the best italian restaurant in SF" });
  console.log(`Agent completed: ${response.success}, answer: ${response.answer}`);
});
```

## Development

### Building the SDK

```bash
# Install dependencies
npm install

# Generate client from OpenAPI spec
npm run generate

# Build the SDK
npm run build

# Run tests
npm test

# Type checking
npm run typecheck
```

### Testing

The SDK includes comprehensive tests:

```bash
# Run all tests
npm test

# Run tests with coverage
npm run test -- --coverage

# Run specific test file
npm run test test/client.test.ts
```

### Regenerating from API

The SDK is auto-generated from the Notte OpenAPI specification:

```bash
# Regenerate client code
npm run generate
```

This will fetch the latest API specification and update the generated client code.

## TypeScript Support

The SDK is built with full TypeScript support:

```typescript
import { NotteClient, type SessionResponse, type LegacyAgentStatusResponse } from 'notte-sdk';

const notte = new NotteClient();

// All types are properly inferred
await notte.Session().use(async (session) => {
  const status: SessionResponse = await session.status();
  const agent = notte.Agent({ session });
  const response: LegacyAgentStatusResponse = await agent.run({ task: "task" });
});
```

## API Reference

### Types

The SDK exports all generated types from the OpenAPI specification alongside the
hand-written option types:

```typescript
import type {
  NotteClientConfig,
  SessionOptions,
  SessionResponse,
  SessionListOptions,
  AgentConstructor,
  AgentRunRequest,
  AgentUpdateHandler,
  AgentListOptions,
  VaultConstructor,
  VaultListOptions,
  CredentialsDictInput,
  Credential,
  PersonaConstructor,
  MessageReadOptions,
  PersonaListOptions,
  FunctionConstructor,
  FunctionListOptions,
  RetryOptions,
  NotteAPIErrorBody,
  SearchOptions,
  SearchResultsResponse,
  AnythingStartResponse,
  SecretMetadata,
  UsageResponse,
} from 'notte-sdk';
```

## License

MIT

## Support

For issues and questions:
- GitHub Issues: [Report issues](https://github.com/nottelabs/notte/issues)
- Documentation: [docs.notte.cc](https://docs.notte.cc)
- Python SDK: [notte-sdk](https://pypi.org/project/notte-sdk/)
