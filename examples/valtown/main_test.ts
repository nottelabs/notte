import assert from "node:assert/strict";
import handler, { readPage } from "./main.ts";

const live = Deno.env.get("NOTTE_VALTOWN_LIVE") === "1";
const fakeKey = "notte-valtown-offline-test-key"; // pragma: allowlist secret
const fakeToken = "valtown-offline-invocation-token"; // pragma: allowlist secret

async function closed(id: string) {
  const root = Deno.env.get("NOTTE_API_URL")!;
  const key = Deno.env.get("NOTTE_API_KEY")!;
  for (let attempt = 0; attempt < 30; attempt++) {
    const response = await fetch(`${root}/sessions/${id}`, {
      headers: { Authorization: `Bearer ${key}` },
      signal: AbortSignal.timeout(15_000),
    });
    assert.ok(response.ok, `Session status returned HTTP ${response.status}`);
    if ((await response.json()).status === "closed") return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert.fail("The owned browser session did not close");
}

async function owned<T>(operation: () => Promise<T>, failure = false) {
  const original = globalThis.fetch;
  const ids: string[] = [], stopped: string[] = [];
  const originalKey = Deno.env.get("NOTTE_API_KEY");
  const originalUrl = Deno.env.get("NOTTE_API_URL");
  if (live) assert.ok(originalUrl, "Choose the browser API explicitly");
  else {
    Deno.env.set("NOTTE_API_KEY", fakeKey);
    Deno.env.set("NOTTE_API_URL", "https://notte.example.invalid");
  }
  globalThis.fetch = async (input, init) => {
    const request = new Request(input, init);
    const path = new URL(request.url).pathname;
    if (live) {
      const response = await original(request);
      if (path === "/sessions/start" && response.ok) {
        ids.push((await response.clone().json()).session_id);
      }
      return response;
    }
    assert.equal(request.headers.get("Authorization"), `Bearer ${fakeKey}`);
    if (path === "/sessions/start") {
      const id = crypto.randomUUID();
      ids.push(id);
      return Response.json({ session_id: id, status: "active" });
    }
    assert.ok(ids.length === 1 && path.startsWith(`/sessions/${ids[0]}/`));
    if (path.endsWith("/stop")) {
      stopped.push(ids[0]);
      return Response.json({ session_id: ids[0], status: "closed" });
    }
    assert.ok(path.endsWith("/page/execute"));
    const action = await request.json();
    if (failure && action.type === "goto") {
      return Response.json({ detail: "Navigation unavailable" }, {
        status: 400,
      });
    }
    return Response.json({
      success: true,
      message: "Done",
      action,
      data: action.type === "evaluate_js"
        ? { markdown: "Example Domain" }
        : undefined,
    });
  };
  try {
    return { result: await operation(), ids };
  } finally {
    globalThis.fetch = original;
    try {
      if (live) { for (const id of ids) await closed(id); }
      else assert.deepEqual(stopped, ids);
      assert.equal(ids.length, 1);
    } finally {
      if (originalKey === undefined) Deno.env.delete("NOTTE_API_KEY");
      else Deno.env.set("NOTTE_API_KEY", originalKey);
      if (originalUrl === undefined) Deno.env.delete("NOTTE_API_URL");
      else Deno.env.set("NOTTE_API_URL", originalUrl);
    }
  }
}

Deno.test("The HTTP handler rejects unauthenticated requests without creating browsers", async () => {
  const original = globalThis.fetch;
  Deno.env.set("NOTTE_VALTOWN_TOKEN", fakeToken);
  globalThis.fetch = () => {
    throw new Error("Unauthorized requests must not reach Notte");
  };
  try {
    assert.equal(
      (await handler(new Request("https://val.example", { method: "POST" })))
        .status,
      401,
    );
    assert.equal(
      (await handler(new Request("https://val.example"))).status,
      405,
    );
  } finally {
    globalThis.fetch = original;
  }
});

Deno.test("The authenticated HTTP task returns the title after closing its browser", async () => {
  Deno.env.set("NOTTE_VALTOWN_TOKEN", fakeToken);
  const { result, ids } = await owned(() =>
    handler(
      new Request("https://val.example", {
        method: "POST",
        headers: { Authorization: `Bearer ${fakeToken}` },
      }),
    )
  );
  assert.equal(result.status, 200);
  assert.deepEqual(await result.json(), {
    title: "Example Domain",
    session_id: ids[0],
  });
});

Deno.test("Navigation failure closes the owned browser", async () => {
  await assert.rejects(owned(() => readPage("http://127.0.0.1:1"), true));
});

Deno.test(
  "The HTTP task returns a safe error after cleanup",
  { ignore: live },
  async () => {
    Deno.env.set("NOTTE_VALTOWN_TOKEN", fakeToken);
    const { result } = await owned(() =>
      handler(
        new Request("https://val.example", {
          method: "POST",
          headers: { Authorization: `Bearer ${fakeToken}` },
        }),
      ), true);
    assert.equal(result.status, 502);
    assert.deepEqual(await result.json(), { error: "Browser task failed" });
  },
);
