// @sniptest filename=param_use_vision.ts
// @sniptest show=7-10
import assert from 'node:assert/strict';
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const agent = client.Agent({
    session,
    use_vision: true, // Agent can understand images
  });
  const status = await session.status();
  assert.equal(agent['request']?.session_id, status.session_id);
  assert.equal(agent['request']?.use_vision, true);
  return status;
});

export { status };
