import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { test } from "node:test";
import { chromium, type Browser } from "playwright-core";
import { CA_SHA256, Notte, createToken, disconnect, fillPassword } from "../src/index.js";

const id = "11111111-1111-4111-8111-111111111111";
const target = new URL("https://login.example.test/form");
const proxy = {
  type: "external" as const,
  server: "https://us-va.browser.relay.evervault.app:443",
  username: "fixture-app",
  password: "fixture-proxy-jwe", // pragma: allowlist secret (dummy fixture)
};
const markers = {
  "X-Notte-Browser-Trust-Profile": "evervault",
  "X-Notte-Browser-Trust-SHA256": CA_SHA256,
};

async function fixture(
  headers: Record<string, string> = markers,
  fail = false,
  startStatus = 200,
  onStart?: () => Promise<void>,
) {
  const requests: { path: string; method: string; auth?: string; body: any }[] =
    [];
  const server = createServer(async (req, res) => {
    let body = "";
    for await (const chunk of req) body += chunk;
    requests.push({
      path: req.url!,
      method: req.method!,
      auth: req.headers.authorization,
      body: body ? JSON.parse(body) : undefined,
    });
    res.setHeader("Content-Type", "application/json");
    if (req.url === "/browser-tokens") {
      res.statusCode = fail ? 401 : 200;
      res.end(
        JSON.stringify(
          fail
            ? { error: proxy.password }
            : {
                data: [
                  {
                    id: "login-password",
                    category: "credential.password",
                    value: "fixture-browser-token",
                  },
                ],
                proxyConfiguration: {
                  hostname: "us-va.browser.relay.evervault.app",
                  port: 443,
                  username: proxy.username,
                  password: proxy.password,
                },
                expiresAt: new Date(Date.now() + 300_000).toISOString(),
              },
        ),
      );
    } else if (req.url === "/sessions/start") {
      await onStart?.();
      res.statusCode = startStatus;
      for (const [name, value] of Object.entries(headers))
        res.setHeader(name, value);
      res.end(
        JSON.stringify({
          session_id: id,
          cdp_url: "wss://cdp.example.test/fixture",
        }),
      );
    } else if (req.url === `/sessions/${id}/stop`) res.end("{}");
    else if (req.url === `/sessions/${id}`) res.end('{"status":"closed"}');
    else {
      res.statusCode = 404;
      res.end("{}");
    }
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address !== "string");
  return {
    root: `http://127.0.0.1:${address.port}`,
    requests,
    close: () =>
      new Promise<void>((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve())),
      ),
  };
}

function browserFixture(fail = false) {
  const state = { connected: 0, closed: 0, token: "" };
  const browser = {
    contexts: () => [
      {
        newPage: async () => ({
          goto: async () => {
            if (fail) throw new Error(proxy.password);
          },
          url: () => target.href,
          locator: () => ({
            fill: async (value: string) => {
              state.token = value;
            },
          }),
        }),
      },
    ],
    close: async () => {
      state.closed++;
    },
  } as unknown as Browser;
  return {
    state,
    connect: async (_url: string) => {
      state.connected++;
      return browser;
    },
  };
}

test("native HTTP contracts keep encrypted input and app credentials out of Notte", async () => {
  const f = await fixture();
  const browser = browserFixture();
  try {
    const result = await createToken(
      "fixture-app",
      "fixture-evervault-key",
      "ev:fixture-encrypted",
      target,
      `${f.root}/browser-tokens`,
    );
    await fillPassword(
      new Notte("fixture-notte-key", f.root),
      result.proxy,
      result.token,
      target,
      undefined,
      browser.connect,
    );
    const [vendor, start, stop, status] = f.requests;
    assert.equal(
      vendor.auth,
      `Basic ${Buffer.from("fixture-app:fixture-evervault-key").toString("base64")}`,
    );
    assert.deepEqual(vendor.body.permissions, [
      { action: "decrypt", target: "login.example.test" },
    ]);
    assert.equal(vendor.body.ttl, 300);
    assert.equal(vendor.body.data[0].value, "ev:fixture-encrypted");
    assert.equal(start.body.browser_trust_profile, "evervault");
    assert.deepEqual(start.body.proxies, [proxy]);
    assert(!JSON.stringify(start).includes("ev:fixture-encrypted"));
    assert(!JSON.stringify(start).includes("fixture-evervault-key"));
    assert.equal(start.auth, "Bearer fixture-notte-key");
    assert.equal(browser.state.token, "fixture-browser-token");
    assert.equal(stop.method, "DELETE");
    assert.equal(status.path, `/sessions/${id}`);
    assert.equal(browser.state.closed, 1);
  } finally {
    await f.close();
  }
});

const unverified: Record<string, string>[] = [
  {},
  { ...markers, "X-Notte-Browser-Trust-SHA256": "wrong" },
  { "X-Notte-Browser-Trust-Profile": "evervault" },
  { "X-Notte-Browser-Trust-SHA256": CA_SHA256 },
];
for (const headers of unverified) {
  test(`missing or mismatched attestation closes before CDP: ${JSON.stringify(headers)}`, async () => {
    const f = await fixture(headers);
    const browser = browserFixture();
    try {
      await assert.rejects(
        fillPassword(
          new Notte("fixture-notte-key", f.root),
          proxy,
          "fixture-token",
          target,
          undefined,
          browser.connect,
        ),
        /trust was not verified/,
      );
      assert.equal(browser.state.connected, 0);
      assert.deepEqual(
        f.requests.map((r) => r.method),
        ["POST", "DELETE", "GET"],
      );
    } finally {
      await f.close();
    }
  });
}

test("vendor HTTP errors do not include returned credentials", async () => {
  const f = await fixture(markers, true);
  try {
    await assert.rejects(
      createToken(
        "fixture-app",
        "fixture-key",
        "ev:fixture",
        target,
        `${f.root}/browser-tokens`,
      ),
      { message: "Evervault returned HTTP 401" },
    );
  } finally {
    await f.close();
  }
});

test("a failed start response with an owned ID still stops and confirms closure", async () => {
  const f = await fixture(markers, false, 502);
  const browser = browserFixture();
  try {
    await assert.rejects(
      fillPassword(
        new Notte("fixture-key", f.root),
        proxy,
        "fixture-token",
        target,
        undefined,
        browser.connect,
      ),
      { message: "Notte start failed (HTTP 502)" },
    );
    assert.equal(browser.state.connected, 0);
    assert.deepEqual(
      f.requests.map((r) => r.method),
      ["POST", "DELETE", "GET"],
    );
  } finally {
    await f.close();
  }
});

test("browser failure redacts the cause and still stops and confirms closure", async () => {
  const f = await fixture();
  const browser = browserFixture(true);
  try {
    await assert.rejects(
      fillPassword(
        new Notte("fixture-key", f.root),
        proxy,
        "fixture-token",
        target,
        undefined,
        browser.connect,
      ),
      { message: "Browser token form fill failed" },
    );
    assert.equal(browser.state.closed, 1);
    assert.deepEqual(
      f.requests.map((r) => r.method),
      ["POST", "DELETE", "GET"],
    );
  } finally {
    await f.close();
  }
});

test("pre-cancelled caller still recovers and closes its owned start", async () => {
  const f = await fixture();
  const browser = browserFixture();
  try {
    await assert.rejects(
      fillPassword(
        new Notte("fixture-key", f.root),
        proxy,
        "fixture-token",
        target,
        AbortSignal.abort(),
        browser.connect,
      ),
    );
    assert.equal(browser.state.connected, 0);
    assert.deepEqual(
      f.requests.map((r) => r.method),
      ["POST", "DELETE", "GET"],
    );
  } finally {
    await f.close();
  }
});

test("cancellation during a pending browser action disconnects and closes ownership", async () => {
  const f = await fixture();
  const controller = new AbortController();
  let started!: () => void, rejectNavigation!: (reason: Error) => void;
  const entered = new Promise<void>((resolve) => {
    started = resolve;
  });
  const page = {
    goto: () =>
      new Promise<void>((_resolve, reject) => {
        rejectNavigation = reject;
        started();
      }),
  };
  const browser = {
    contexts: () => [{ newPage: async () => page }],
    close: async () => {
      rejectNavigation?.(new Error("fixture-private-detail"));
    },
  } as unknown as Browser;
  try {
    const run = fillPassword(
      new Notte("fixture-key", f.root),
      proxy,
      "fixture-token",
      target,
      controller.signal,
      async () => browser,
    );
    const result = assert.rejects(run, {
      message: "Browser token form fill failed",
    });
    await entered;
    controller.abort();
    await result;
    assert.deepEqual(
      f.requests.map((r) => r.method),
      ["POST", "DELETE", "GET"],
    );
  } finally {
    await f.close();
  }
});

test(
  "an unresponsive CDP disconnect cannot prevent owned DELETE and GET closure",
  { timeout: 10_000 },
  async () => {
    const f = await fixture();
    const browser = browserFixture();
    const connect = async (url: string) => {
      const value = await browser.connect(url);
      value.close = () => new Promise<void>(() => {});
      return value;
    };
    try {
      await assert.rejects(
        fillPassword(
          new Notte("fixture-key", f.root),
          proxy,
          "fixture-token",
          target,
          undefined,
          connect,
        ),
        { message: "Browser disconnect failed" },
      );
      assert.deepEqual(
        f.requests.map((r) => r.method),
        ["POST", "DELETE", "GET"],
      );
    } finally {
      await f.close();
    }
  },
);

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  test(
    `native CLI ${signal} during startup recovers its response and closes ownership`,
    { timeout: 60_000 },
    async () => {
      let entered!: () => void, release!: () => void;
      const started = new Promise<void>((resolve) => {
        entered = resolve;
      });
      const response = new Promise<void>((resolve) => {
        release = resolve;
      });
      const f = await fixture(markers, false, 200, async () => {
        entered();
        await response;
      });
      const script = `import { main } from ${JSON.stringify(new URL("../src/index.ts", import.meta.url).href)}; main(async () => ({token:'fixture-token',proxy:${JSON.stringify(proxy)}})).catch(() => { process.exitCode=1; });`;
      const child = spawn(
        process.execPath,
        ["--import", "tsx", "--input-type=module", "-e", script],
        {
          env: {
            PATH: process.env.PATH,
            NOTTE_API_KEY: "fixture-notte-key", // pragma: allowlist secret (dummy fixture)
            NOTTE_API_URL: f.root,
            EVERVAULT_APP_ID: "fixture-app",
            EVERVAULT_API_KEY: "fixture-vendor-key", // pragma: allowlist secret (dummy fixture)
            EVERVAULT_ENCRYPTED_PASSWORD: "ev:fixture", // pragma: allowlist secret (dummy fixture)
            EVERVAULT_FORM_URL: target.href,
          },
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      const exited = once(child, "exit");
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        await Promise.race([
          started,
          exited.then(([code]) => {
            throw new Error(`CLI exited before startup (${code})`);
          }),
          new Promise<never>((_resolve, reject) => {
            timer = setTimeout(
              () => reject(new Error("CLI startup timed out")),
              45_000,
            );
          }),
        ]);
        clearTimeout(timer);
        child.kill(signal);
        // Let the real signal handler run while the start response is still pending.
        await new Promise((resolve) => setTimeout(resolve, 100));
        release();
        const [code, termination] = await exited;
        assert.equal(code, 1);
        assert.equal(termination, null);
        assert.deepEqual(
          f.requests.map((r) => r.method),
          ["POST", "DELETE", "GET"],
        );
      } finally {
        clearTimeout(timer);
        release();
        if (child.exitCode === null) child.kill("SIGKILL");
        await f.close();
      }
    },
  );
}

test("invalid target or plaintext input fails before the vendor request", async () => {
  await assert.rejects(
    createToken("app", "key", "plaintext", target),
    /encrypted value/,
  );
  await assert.rejects(
    createToken(
      "app",
      "key",
      "ev:fixture",
      new URL("http://login.example.test"),
    ),
    /HTTPS/,
  );
});

const live = process.env.NOTTE_EVERVAULT_LIVE === "1";
class ObservedNotte extends Notte {
  override async close(id: string) {
    await super.close(id);
    console.log(`Owned browser closed: ${id}`);
  }
}
test(
  "live native Notte browser control fills an owned dummy form and closes",
  { skip: !live, timeout: 120_000 },
  async () => {
    assert(process.env.NOTTE_API_KEY);
    const notte = new ObservedNotte(
      process.env.NOTTE_API_KEY,
      process.env.NOTTE_API_URL,
    );
    await notte.owned(
      { max_duration_minutes: 3, proxies: false },
      async (_id, cdp) => {
        const browser = await chromium.connectOverCDP(await cdp(), {
          timeout: 30_000,
        });
        try {
          const page = await browser.contexts()[0].newPage();
          await page.goto("https://example.com", {
            waitUntil: "domcontentloaded",
          });
          await page.setContent(
            '<form><input name="password" type="password"></form>',
          );
          await page.locator('[name="password"]').fill("fixture-browser-token");
          assert.equal(
            await page.locator('[name="password"]').inputValue(),
            "fixture-browser-token",
          );
        } finally {
          await disconnect(browser);
        }
      },
      false,
    );
  },
);

test(
  "live unknown-profile gate never hands out CDP and closes any returned ID",
  { skip: !live, timeout: 120_000 },
  async () => {
    assert(process.env.NOTTE_API_KEY);
    const notte = new ObservedNotte(
      process.env.NOTTE_API_KEY,
      process.env.NOTTE_API_URL,
    );
    await assert.rejects(
      notte.owned(
        {
          max_duration_minutes: 3,
          proxies: false,
          browser_trust_profile: "__unknown_profile__",
        },
        async () => {
          assert.fail("Unverified profile reached browser work");
        },
      ),
      /trust was not verified|Notte start returned no owned ID \(HTTP (400|422)\)/,
    );
  },
);

test(
  "explicit supported-profile acceptance verifies the Notte runtime without vendor credentials",
  { skip: process.env.NOTTE_EVERVAULT_PROFILE_LIVE !== "1", timeout: 120_000 },
  async () => {
    assert(process.env.NOTTE_API_KEY);
    const notte = new ObservedNotte(
      process.env.NOTTE_API_KEY,
      process.env.NOTTE_API_URL,
    );
    await notte.owned(
      {
        max_duration_minutes: 3,
        proxies: false,
        browser_trust_profile: "evervault",
      },
      async (_id, cdp) => {
        const browser = await chromium.connectOverCDP(await cdp(), {
          timeout: 30_000,
        });
        try {
          const page = await browser.contexts()[0].newPage();
          await page.goto("https://example.com", {
            waitUntil: "domcontentloaded",
          });
          assert.equal(await page.title(), "Example Domain");
          await page.setContent(
            '<form><input name="password" type="password"></form>',
          );
          await page.locator('[name="password"]').fill("fixture-browser-token");
          assert.equal(
            await page.locator('[name="password"]').inputValue(),
            "fixture-browser-token",
          );
        } finally {
          await disconnect(browser);
        }
      },
    );
  },
);
