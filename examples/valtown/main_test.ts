import assert from "node:assert/strict";
import handler, { readPage } from "./main.ts";

const live = Deno.env.get("NOTTE_VALTOWN_LIVE") === "1";
const fakeKey = "notte-valtown-offline-test-key"; // pragma: allowlist secret
const fakeToken = "valtown-offline-invocation-token"; // pragma: allowlist secret

async function closed(id: string) {
  const root = Deno.env.get("NOTTE_API_URL")!;
  const key = Deno.env.get("NOTTE_API_KEY")!;
  const signal = AbortSignal.timeout(15_000);
  while (!signal.aborted) {
    const response = await fetch(`${root}/sessions/${id}`, {
      headers: { Authorization: `Bearer ${key}` },
      signal,
    });
    assert.ok(response.ok, `Session status returned HTTP ${response.status}`);
    if ((await response.json()).status === "closed") return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert.fail("The owned browser session did not close");
}

async function owned<T>(
  operation: () => Promise<T>,
  failure = false,
  stopFailure = false,
) {
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
      if (path.endsWith("/stop") && stopFailure) {
        // Inject the failed response after the real owned stop completes.
        await response.body?.cancel();
        return Response.json({ detail: "PRIVATE_STOP_BODY" }, { status: 503 });
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
      if (stopFailure) {
        return Response.json({ detail: "PRIVATE_STOP_BODY" }, { status: 503 });
      }
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
  await owned(() => assert.rejects(() => readPage("http://127.0.0.1:1")), true);
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

Deno.test("A cleanup failure preserves the original task failure", async () => {
  const original = console.error;
  const messages: string[] = [];
  console.error = (...values) => messages.push(values.join(" "));
  try {
    await owned(
      () =>
        assert.rejects(
          () => readPage("http://127.0.0.1:1"),
          (error: unknown) => {
            assert.ok(error instanceof Error);
            assert.notEqual(error.message, "Notte API returned HTTP 503");
            if (!live) {
              assert.equal(error.message, "Notte API returned HTTP 400");
            }
            return true;
          },
        ),
      true,
      true,
    );
    assert.deepEqual(messages, [
      "Notte browser cleanup failed: Notte API returned HTTP 503",
    ]);
  } finally {
    console.error = original;
  }
});

Deno.test("A successful task still reports a cleanup failure", async () => {
  const original = console.error;
  const messages: string[] = [];
  console.error = (...values) => messages.push(values.join(" "));
  try {
    await owned(
      () =>
        assert.rejects(
          () => readPage(),
          /Notte API returned HTTP 503/,
        ),
      false,
      true,
    );
    assert.deepEqual(messages, [
      "Notte browser cleanup failed: Notte API returned HTTP 503",
    ]);
  } finally {
    console.error = original;
  }
});

Deno.test("Handler diagnostics exclude raw transport and parser details", {
  ignore: live,
}, async () => {
  const fetch = globalThis.fetch, log = console.error;
  const key = Deno.env.get("NOTTE_API_KEY"),
    url = Deno.env.get("NOTTE_API_URL");
  const messages: string[] = [];
  Deno.env.set("NOTTE_API_KEY", fakeKey);
  Deno.env.set("NOTTE_API_URL", "https://notte.example.invalid");
  Deno.env.set("NOTTE_VALTOWN_TOKEN", fakeToken);
  console.error = (...values) => messages.push(values.join(" "));
  const request = () =>
    new Request("https://val.example", {
      method: "POST",
      headers: { Authorization: `Bearer ${fakeToken}` },
    });
  try {
    for (
      const error of [
        new Error(`PRIVATE_TRANSPORT ${fakeKey} ${fakeToken}`),
        new SyntaxError("PRIVATE_JSON_BODY"),
        new DOMException("PRIVATE_TIMEOUT_URL", "TimeoutError"),
      ]
    ) {
      globalThis.fetch = () => Promise.reject(error);
      const response = await handler(request());
      assert.equal(response.status, 502);
      assert.deepEqual(await response.json(), { error: "Browser task failed" });
    }
    Deno.env.delete("NOTTE_API_KEY");
    assert.equal((await handler(request())).status, 502);
    assert.deepEqual(messages, [
      "Notte browser task failed: Unexpected browser task failure",
      "Notte browser task failed: Unexpected browser task failure",
      "Notte browser task failed: Notte request timed out",
      "Notte browser task failed: Set NOTTE_API_KEY",
    ]);
    assert.ok(!messages.join(" ").includes("PRIVATE_"));
    assert.ok(!messages.join(" ").includes(fakeKey));
    assert.ok(!messages.join(" ").includes(fakeToken));
  } finally {
    globalThis.fetch = fetch;
    console.error = log;
    if (key === undefined) Deno.env.delete("NOTTE_API_KEY");
    else Deno.env.set("NOTTE_API_KEY", key);
    if (url === undefined) Deno.env.delete("NOTTE_API_URL");
    else Deno.env.set("NOTTE_API_URL", url);
  }
});
