// @sniptest filename=context_manager.ts
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

await client.Session({ idle_timeout_minutes: 2 }).use(async (session) => {
  console.log(session.getId());
});
// Automatically stopped here, including when the callback throws.
