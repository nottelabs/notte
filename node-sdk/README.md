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
npx vitest run test/function-stream.integration.test.ts
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
CI runs credential-free checks on pull requests, including forks. Live tests and
API drift checks run on main pushes or a manual workflow run on main.

### Releases

The npm package remains `notte-sdk`. Its MIT license is in [LICENSE](LICENSE);
the repository root license does not replace this package's license.

Publishing is disabled by default. Before enabling it, maintainers must:

1. Disable the previous publishing workflow.
2. Configure npm trusted publishing for `nottelabs/notte`, workflow
   `node-sdk-publish.yml`, environment `npm`, and configure environment protection.
3. Set the repository variable `NODE_SDK_PUBLISH_ENABLED=true`.

Publishing a stable GitHub release tagged `node-sdk-vX.Y.Z` then runs validation
and publishes with provenance. Python release tags do not trigger npm publishing.
No registry credentials or publishing configuration are changed by adding this package.

## Features

- 🌐 **Cloud Browser Sessions** - Access remote browsers with full control
- 🤖 **LLM-Powered Agents** - Intelligent web automation with natural language
- 🔒 **Secret Vaults** - Enterprise-grade credential management with end-to-end encryption
- 👤 **Digital Personas** - Complete identities with email, SMS, and 2FA for automated account creation
- 🎯 **Session Management** - Context managers for reliable resource cleanup
- 📡 **Real-time Updates** - WebSocket support for live agent monitoring
- 📝 **Type Safety** - Full TypeScript support with generated types
- ⚡ **Serverless Functions** - Run pre-built automation workflows with simple API calls
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
await notte.Session({ timeoutMinutes: 30 }).use(async (session) => {
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

  const response = await agent.run(
    "Find the best Italian restaurant in San Francisco and book a table for 2 at 7pm today",
    (update) => {
      // Receive real-time updates via WebSocket
      console.log(`Step ${update.data.currentStep}: ${update.data.message}`);
    }
  );

  console.log(`Agent completed: ${response.success ? 'Success' : 'Failed'}`);
  console.log(`Answer: ${response.answer}`);
});
```

## Core Classes

### NotteClient

The main client for interacting with the Notte API.

```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient();

// Create sessions
const session = notte.Session({ timeoutMinutes: 30 });

// Create agents
const agent = notte.Agent({ session, max_steps: 15 });

// Create vaults
const vault = notte.Vault({ name: 'My Vault' });

// Create personas
const persona = notte.Persona({ create_vault: true });
```

### Session

Manages browser sessions with automatic lifecycle management.

```typescript
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient();

// Context manager pattern (automatic start/stop)
await notte.Session({ timeoutMinutes: 30 }).use(async (session) => {
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
for await (const session of notte.Session({ timeoutMinutes: 15 })) {
  // Use session here
  const status = await session.status();
  console.log('Session active:', status);
  // Session automatically closed after loop
}
```

#### Session Methods

- `start()` - Start the session
- `stop()` - Stop the session
- `status()` - Get session status
- `viewer()` - Open the live session viewer in the local default browser
- `use(callback)` - Context manager pattern
- `getId()` - Get session ID
- `isSessionActive()` - Check if session is running

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

  // Non-blocking: start agent and get ID
  const agentId = await agent.start("Navigate to Google and search for 'TypeScript'");
  console.log('Agent started:', agentId);

  // Check agent status
  const status = await agent.status();
  console.log('Agent status:', status);

  // Blocking: run agent and wait for completion with live updates
  const response = await agent.run(
    "Find the latest TypeScript documentation",
    (update) => {
      if (update.type === 'step') {
        console.log(`Step update:`, update.data);
      } else if (update.type === 'completion') {
        console.log(`Completed:`, update.data);
      }
    }
  );

  console.log('Final result:', response);
});
```

#### Agent Methods

- `start(task)` - Start agent with task (non-blocking)
- `run(task, onUpdate?)` - Start agent and wait for completion (blocking)
- `status()` - Get agent status
- `stop()` - Stop the agent
- `getId()` - Get agent ID
- `isRunning()` - Check if agent is running

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

// Add credit card information
await vault.setCreditCard({
  card_holder_name: 'John Doe',
  card_number: '4111111111111111',
  card_cvv: '123',
  expiry_month: '12',
  expiry_year: '2025'
});

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
await vault.deleteCreditCard();
await vault.stop(); // Deletes entire vault
```

#### Vault Methods

- `addCredentials(url, credentials)` - Store credentials for a URL
- `getCredentials(url)` - Retrieve credentials for a URL
- `deleteCredentials(url)` - Delete credentials for a URL
- `listCredentials()` - List all stored credentials
- `setCreditCard(card)` - Store credit card information
- `getCreditCard()` - Retrieve credit card information
- `deleteCreditCard()` - Delete credit card information
- `generatePassword(length?, includeSpecialChars?)` - Generate secure passwords
- `delete()` - Delete the entire vault
- `stop()` - Stop and delete the vault

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

// Create a new persona with vault and phone number
const persona = notte.Persona({
  create_vault: true,
  create_phone_number: true
});

// Get persona information
console.log(`Email: ${persona.info.email}`);
console.log(`Phone: ${persona.info.phone_number}`);

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

  const result = await agent.run(
    `Create an account on GitHub using the persona credentials`
  );
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

- `emails(options?)` - Read emails sent to the persona
- `sms(options?)` - Read SMS messages sent to the persona
- `createNumber(options?)` - Create a phone number for the persona
- `deleteNumber()` - Delete the persona's phone number
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

- **Complete Digital Identity** - Unique email address and phone number
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

#### Function Methods

- `run(variables?, options?)` - Stream logs and wait for completion; use `stream: false` for the backend's JSON response without live logs
- `createRun()` - Create a cloud run record without executing it
- `getRun(functionRunId)` - Get current metadata/result for a specific run
- `retrieve(functionRunId)` - Compatibility alias for `getRun()`
- `download(options?)` - Download the function code, optionally writing it to `options.path`
- `getUrl(options?)` - Get the (decrypted) download url of the function code
- `getFunctionId()` - Get the function ID
- `functionId` - The function ID (read-only property)
- `decryptionKey` - The decryption key, if provided (read-only property)

## Advanced Usage

### Session Configuration

```typescript
const session = notte.Session({
  timeoutMinutes: 45,        // Session timeout (default: 30)
  // Add other session options as supported by the API
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

```typescript
try {
  await notte.Session().use(async (session) => {
    const agent = notte.Agent({ session });
    const response = await agent.run("Complete a complex task");

    if (!response.success) {
      console.error('Agent failed:', response.error);
    }
  });
} catch (error) {
  console.error('Session error:', error);
}
```

### WebSocket Updates

The `agent.run()` method provides real-time updates via WebSocket:

```typescript
const response = await agent.run("Your task", (update) => {
  switch (update.type) {
    case 'step':
      console.log(`Step ${update.data.currentStep}:`, update.data);
      break;
    case 'completion':
      console.log('Task completed:', update.data);
      break;
    default:
      console.log('Update:', update);
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
with notte.Session(timeout_minutes=2) as session:
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
await notte.Session({ timeoutMinutes: 2 }).use(async (session) => {
  const status = await session.status();
  console.log(status);
});

// Agent usage
await notte.Session().use(async (session) => {
  const agent = notte.Agent({ session, max_steps: 10 });
  const response = await agent.run("Find the best italian restaurant in SF");
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
npm run test src/test/client.test.ts
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
import { NotteClient, SessionStatus, AgentResponse } from 'notte-sdk';

const notte = new NotteClient();

// All types are properly inferred
await notte.Session().use(async (session) => {
  const status: SessionStatus = await session.status();
  const agent = notte.Agent({ session });
  const response: AgentResponse = await agent.run("task");
});
```

## API Reference

### Types

The SDK exports all generated types from the OpenAPI specification:

```typescript
import type {
  NotteClientConfig,
  SessionOptions,
  SessionStatus,
  AgentConstructor,
  AgentRunRequest,
  AgentUpdateHandler,
  VaultConstructor,
  CredentialsDict,
  CreditCardDict,
  Credential,
  PersonaConstructor,
  MessageReadOptions,
  PersonaListOptions,
  CreatePhoneNumberOptions
} from 'notte-sdk';
```

## License

MIT

## Support

For issues and questions:
- GitHub Issues: [Report issues](https://github.com/nottelabs/notte/issues)
- Documentation: [docs.notte.cc](https://docs.notte.cc)
- Python SDK: [notte-sdk](https://pypi.org/project/notte-sdk/)
