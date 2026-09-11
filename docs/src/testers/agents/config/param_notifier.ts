// @sniptest filename=param_notifier.ts
// @sniptest show=6-12
import assert from 'node:assert/strict';
import { NotteClient, sessionStatus } from 'notte-sdk';

const client = new NotteClient();

const agent = await client.Session().use(async session =>
  // Agent with notification via email
  client.Agent({
    session,
    // Notifications can be configured in the Notte console
  }),
);

const sessionId = agent['request']?.session_id;
assert.ok(sessionId);
const { data: status } = await sessionStatus({
  client: client.getClient(), path: { session_id: sessionId }, throwOnError: true,
});
assert.equal(status.session_id, sessionId);

export { status };
