// @sniptest filename=param_reasoning_model.ts
// @sniptest show=7-7
import assert from 'node:assert/strict';
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const agent = client.Agent({ session, reasoning_model: 'anthropic/claude-3.5-sonnet' });
  const status = await session.status();
  assert.equal(agent['request']?.reasoning_model, 'anthropic/claude-3.5-sonnet');
  assert.equal(agent['request']?.session_id, status.session_id);
  return status;
});

export { status };
