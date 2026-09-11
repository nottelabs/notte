// @sniptest filename=stop_session.ts
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Manual lifecycle: always stop in finally.
const session = client.Session({ idle_timeout_minutes: 2 });
await session.start();
try {
  const status = await session.status();
  if (status.status !== 'active') throw new Error('Session is not active');
  console.log(
    JSON.stringify({
      session_id: session.getId(),
      status: status.status,
      idle_timeout_minutes: status.idle_timeout_minutes,
    }),
  );
} finally {
  await session.stop();
}
