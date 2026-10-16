import { pathToFileURL } from "node:url";

type Transport = typeof fetch;
type Account = { id: string; app: { nameSlug: string } | null; healthy: boolean | null };
type App = { nameSlug: string; authType: string };
type Action = { key: string; name: string; description: string };

async function request<T>(
  apiKey: string,
  path: string,
  body?: Record<string, unknown>,
  transport: Transport = fetch,
): Promise<T> {
  const response = await transport(`https://www.quaso.ai/api/integrations/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    redirect: "error",
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) throw new Error(`Connected apps request failed: HTTP ${response.status}`);
  return response.json();
}

export async function discover(apiKey: string, app = "github", transport: Transport = fetch) {
  const apps = await request<{ data: App[] }>(apiKey, `apps?${new URLSearchParams({ slug: app })}`, undefined, transport);
  const accounts = await request<{ data: Account[] }>(apiKey, "accounts", undefined, transport);
  const actions = await request<{ data: Action[] }>(apiKey, `actions?${new URLSearchParams({ app, limit: "10" })}`, undefined, transport);
  return {
    apps: apps.data,
    accounts: accounts.data.filter((account) => account.app?.nameSlug === app),
    actions: actions.data,
  };
}

export async function runAction(
  apiKey: string,
  accountId: string,
  actionKey: string,
  configuredProps: Record<string, unknown>,
  transport: Transport = fetch,
) {
  const response = await request<{ result: unknown }>(apiKey, "actions-run", { accountId, actionKey, configuredProps }, transport);
  return response.result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const key = process.env.NOTTE_API_KEY;
  if (!key) throw new Error("Set NOTTE_API_KEY for your Quaso workspace");
  const result = await discover(key, process.env.CONNECTED_APP || "github");
  console.log(JSON.stringify(Object.fromEntries(Object.entries(result).map(([name, items]) => [name, items.length]))));
}
