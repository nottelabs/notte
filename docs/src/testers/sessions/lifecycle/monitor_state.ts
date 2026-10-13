// @sniptest filename=monitor_state.ts
// @sniptest show=6-12
import { NotteClient, type SessionResponse } from 'notte-sdk';

const client = new NotteClient();
let status: SessionResponse | undefined;

const session = client.Session();
await session.use(async () => {
  status = await session.status();
  if (status.status !== 'active') throw new Error('Session is not active');
  console.log(`Status: ${status.status}`);
});
// Automatically stopped here.

export { status };
