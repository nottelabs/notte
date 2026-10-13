// @sniptest filename=param_session.ts
// @sniptest show=14-17
import assert from 'node:assert/strict';
import { NotteClient, sessionStatus } from 'notte-sdk';

const client = new NotteClient();
const createAgent = client.Agent.bind(client);
let capturedAgent: ReturnType<NotteClient['Agent']> | undefined;
client.Agent = options => {
  capturedAgent = createAgent(options);
  assert.ok('session' in options && options.session);
  assert.equal(capturedAgent['request']?.session_id, options.session.getId());
  return capturedAgent;
};

await client.Session({ open_viewer: true }).use(async session => {
  const agent = client.Agent({ session });
  // Use the agent here, while its session is active.
});

assert.ok(capturedAgent);
const request = capturedAgent['request'];
assert.ok(request?.session_id);
const { data: status } = await sessionStatus({
  client: client.getClient(), path: { session_id: request.session_id }, throwOnError: true,
});
assert.equal(status.session_id, request.session_id);
export { status };
