// @sniptest filename=timeout_example.ts
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

await client.Session({ idle_timeout_minutes: 15 }).use(async (session) => {
  const status = await session.status();
  if (status.status !== 'active') throw new Error('Session is not active');
  console.log(
    JSON.stringify({
      session_id: session.getId(),
      status: status.status,
      idle_timeout_minutes: status.idle_timeout_minutes,
    }),
  );
});
// Automatically stopped here.
