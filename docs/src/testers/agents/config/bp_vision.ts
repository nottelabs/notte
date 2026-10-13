// @sniptest filename=bp_vision.ts
// @sniptest show=7-11
import assert from 'node:assert/strict';
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  // Text-only site
  const textAgent = client.Agent({ session, use_vision: false });

  // Image-heavy site
  const agent = client.Agent({ session, use_vision: true });
  const status = await session.status();
  assert.equal(textAgent['request']?.use_vision, false);
  assert.equal(textAgent['request']?.session_id, status.session_id);
  assert.equal(agent['request']?.use_vision, true);
  assert.equal(agent['request']?.session_id, status.session_id);
  return status;
});

export { status };
