// @sniptest filename=save_profile.ts
// @sniptest show=1-17
import { NotteClient } from "notte-sdk";

const client = new NotteClient();

// Start a session without a profile, or with a read-only one
const session = client.Session();
await session.use(async (session) => {
  await session.execute({ type: "goto", url: "https://github.com/login" });
  // ... log in ...

  // Save the current browser state into a new profile; the session keeps running
  const profile = await session.saveProfile({ name: "github-login" });
  console.log(profile.profile_id, profile.persisted_domains);

  // Later saves can overwrite the same profile
  await session.saveProfile({ profile_id: profile.profile_id });
});

const status = await session.status();
export { status };
