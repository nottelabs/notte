// @sniptest filename=param_max_steps.ts
// @sniptest show=7-10
import assert from 'node:assert/strict';
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const agent = client.Agent({
    session,
    max_steps: 20, // Allow up to 20 actions
  });
  const status = await session.status();
  assert.equal(agent['request']?.session_id, status.session_id);
  assert.equal(agent['request']?.max_steps, 20);
  return status;
});

export { status };
