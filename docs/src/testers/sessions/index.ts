// @sniptest filename=session.ts
// @sniptest show=1-9
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// The session is automatically stopped when the callback exits.
await client.Session({ idle_timeout_minutes: 2 }).use(async (session) => {
  const status = await session.status();
  console.log(status);
});
