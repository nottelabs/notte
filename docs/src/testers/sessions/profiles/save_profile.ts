// @sniptest filename=save_profile.ts
// @sniptest show=1-18
import { NotteClient } from "notte-sdk";

const client = new NotteClient();

// Start a session without a profile, or with a read-only one
const session = client.Session();
const profile = await session.use(async (session) => {
  await session.execute({ type: "goto", url: "https://example.com" });
  // ... log in ...

  // Save the current browser state into a new profile; the session keeps running
  const profile = await session.saveProfile({ name: "example-login" });
  console.log(profile.profile_id, profile.persisted_domains);

  // Later saves can overwrite the same profile
  const again = await session.saveProfile({ profile_id: profile.profile_id });
  return { ...profile, sameProfile: again.profile_id === profile.profile_id };
});

const results = [profile.name, profile.sameProfile];
await client.profiles.delete(profile.profile_id);
export { results };
