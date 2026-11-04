// @sniptest filename=workspace_session.ts
// @sniptest typecheck_only=true
import { NotteClient, type SecretProxy } from 'notte-sdk';

const client = new NotteClient();

// An entry without `server` uses the workspace's saved secret proxy.
// The published types still require `server` and `hosts`, hence the cast.
const saved = { type: 'secret' } as SecretProxy;
await client.Session({ proxies: [{ type: 'notte' }, saved] }).use(async (session) => {
  console.log(session.getId());
});

// Use the saved secret proxy with a different password for this session
const override = { type: 'secret', password: 'SESSION_PASSWORD' } as SecretProxy;
await client.Session({ proxies: [{ type: 'notte' }, override] }).use(async (session) => {
  console.log(session.getId());
});
