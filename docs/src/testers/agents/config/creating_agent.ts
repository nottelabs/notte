// @sniptest filename=creating_agent.ts
// @sniptest show=1-14
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const agent = await client.Session().use(async session =>
  client.Agent({
    session,
    reasoning_model: 'gemini/gemini-2.0-flash',
    use_vision: true,
    max_steps: 15,
    // vault, // Optional
    // persona, // Optional
  }),
);

import assert from 'node:assert/strict';
import { sessionStatus } from 'notte-sdk';
const request = agent['request'];
assert.ok(request?.session_id);
assert.equal(request.reasoning_model, 'gemini/gemini-2.0-flash');
assert.equal(request.use_vision, true);
assert.equal(request.max_steps, 15);
const { data: status } = await sessionStatus({
  client: client.getClient(), path: { session_id: request.session_id }, throwOnError: true,
});
export { status };
