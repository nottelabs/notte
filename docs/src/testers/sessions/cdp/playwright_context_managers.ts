// @sniptest filename=playwright_context_managers.ts
// @sniptest show=1-9
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  // Your code here

  return await session.status();
});

export { status };
