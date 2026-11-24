// @sniptest filename=import_state.ts
// @sniptest show=1-44
import { NotteClient } from "notte-sdk";
import type { BrowserContext } from "playwright-core";

type StorageState = Awaited<ReturnType<BrowserContext["storageState"]>>;

const client = new NotteClient();

// The result of Playwright's context.storageState() on your previous provider
const state: StorageState = {
  cookies: [
    {
      name: "session_id",
      value: "abc123",
      domain: "example.com",
      path: "/",
      expires: -1,
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    },
  ],
  origins: [{ origin: "https://example.com", localStorage: [{ name: "theme", value: "dark" }] }],
};

const profile = await client.profiles.create({ name: "imported-login" });

// Notte takes local storage as {origin: {key: value}}, so convert storageState()'s lists
const imported = await client.profiles.stateSet(profile.profile_id, {
  cookies: state.cookies,
  local_storage: Object.fromEntries(
    state.origins.map((origin) => [
      origin.origin,
      Object.fromEntries(origin.localStorage.map((item) => [item.name, item.value])),
    ]),
  ),
});
console.log(imported.cookies_count, imported.local_storage_origins);

// Sessions that use the profile start with the imported state
const session = client.Session({ profile: { id: profile.profile_id } });
const theme = await session.use(async (session) => {
  await session.execute({ type: "goto", url: "https://example.com" });
  return await session.evaluateJs("localStorage.getItem('theme')");
});

const results = [imported.cookies_count, imported.local_storage_origins, theme];
await client.profiles.delete(profile.profile_id);
export { results };
