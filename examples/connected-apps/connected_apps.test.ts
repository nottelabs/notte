import assert from "node:assert/strict";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { test } from "node:test";
import { discover, runAction } from "./connected_apps.ts";

test("connected app native HTTP contracts", async (t) => {
  const calls: { method: string; path: string; auth?: string; body: string }[] = [];
  let status = 200;
  const server = createServer(async (req, res) => {
    let body = "";
    for await (const part of req) body += part.toString();
    calls.push({ method: req.method!, path: req.url!, auth: req.headers.authorization, body });
    let data: unknown = { error: "private fixture detail" };
    if (req.url!.includes("/apps?")) data = { data: [{ nameSlug: "github", authType: "oauth" }] };
    else if (req.url!.endsWith("/accounts")) data = { data: [
      { id: "owned", healthy: true, app: { nameSlug: "github" } },
      { id: "other", app: { nameSlug: "gmail" } }, { id: "unknown", app: null },
    ] };
    else if (req.url!.includes("/actions?")) data = { data: [{ key: "github-get-user", name: "Get user" }] };
    else if (req.url!.endsWith("/actions-run")) data = { ok: true, result: { ret: { login: "fixture-user" } } };
    res.writeHead(status, { "Content-Type": "application/json", Location: "/unexpected-redirect" });
    res.end(JSON.stringify(data));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())));
  const port = (server.address() as AddressInfo).port;
  const transport: typeof fetch = (input, init) => {
    const url = new URL(String(input));
    assert.equal(url.origin, "https://www.quaso.ai");
    assert.equal(init?.redirect, "error");
    assert.ok(init?.signal);
    return fetch(`http://127.0.0.1:${port}${url.pathname}${url.search}`, init);
  };

  await t.test("discovery preserves auth and filters accounts", async () => {
    const result = await discover("fixture-token", "github", transport);
    assert.deepEqual(result.accounts.map((account) => account.id), ["owned"]);
    assert.equal(result.actions[0].key, "github-get-user");
    assert.deepEqual(calls.map((call) => call.path), [
      "/api/integrations/apps?slug=github", "/api/integrations/accounts",
      "/api/integrations/actions?app=github&limit=10",
    ]);
    assert.ok(calls.every((call) => call.method === "GET" && call.auth === "Bearer fixture-token"));
  });

  await t.test("read-only action contract", async () => {
    calls.length = 0;
    assert.deepEqual(await runAction("fixture-token", "owned", "github-get-user", { username: "fixture-user" }, transport), { ret: { login: "fixture-user" } });
    assert.deepEqual(calls[0], {
      method: "POST", path: "/api/integrations/actions-run", auth: "Bearer fixture-token",
      body: JSON.stringify({ accountId: "owned", actionKey: "github-get-user", configuredProps: { username: "fixture-user" } }),
    });
  });

  await t.test("HTTP errors preserve status without response body", async () => {
    calls.length = 0;
    status = 401;
    await assert.rejects(discover("fixture-token", "github", transport), (error: Error) => {
      assert.match(error.message, /HTTP 401/);
      assert.doesNotMatch(error.message, /private fixture detail/);
      return true;
    });
    assert.equal(calls.length, 1);
  });

  await t.test("redirects are not followed", async () => {
    calls.length = 0;
    status = 302;
    await assert.rejects(discover("fixture-token", "github", transport));
    assert.equal(calls.length, 1);
  });
});
