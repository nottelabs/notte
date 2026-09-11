// @sniptest filename=param_session.ts
// @sniptest show=6-8
import assert from 'node:assert/strict';
import { NotteClient, sessionStatus } from 'notte-sdk';

const client = new NotteClient();

const agent = await client.Session({ open_viewer: true }).use(async session =>
  client.Agent({ session }),
);

const sessionId = agent['request']?.session_id;
assert.ok(sessionId);
const { data: status } = await sessionStatus({
  client: client.getClient(), path: { session_id: sessionId }, throwOnError: true,
});
assert.equal(status.session_id, sessionId);

export { status };
