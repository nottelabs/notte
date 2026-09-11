// @sniptest filename=stop_session.ts
// @sniptest show=6-14
import { NotteClient, type SessionResponse } from 'notte-sdk';

const client = new NotteClient();
let status: SessionResponse | undefined;

const session = client.Session({ idle_timeout_minutes: 2 });
await session.start();
try {
  status = await session.status();
  if (status.status !== 'active') throw new Error('Session is not active');
} finally {
  await session.stop();
}
console.log('Session stopped successfully');

export { status };
