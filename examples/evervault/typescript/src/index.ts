import { chromium, type Browser } from "playwright-core";
import { pathToFileURL } from "node:url";

export const CA_SHA256 =
  "4137d69968b54bcf27de628e80cbe2535a15604af8b5ed1236831c9285365968"; // pragma: allowlist secret (public CA fingerprint)
type Proxy = {
  type: "external";
  server: string;
  username: string;
  password: string;
};
type Connect = (url: string) => Promise<Browser>;
const sessionId = (value: unknown): value is string =>
  typeof value === "string" &&
  /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value);

export class Notte {
  constructor(
    private key: string,
    private root = "https://api.notte.cc",
  ) {
    const url = new URL(root);
    if (
      url.protocol !== "https:" &&
      !(url.protocol === "http:" && url.hostname === "127.0.0.1")
    )
      throw new Error("Use an HTTPS Notte API URL");
  }
  async request(
    path: string,
    method = "GET",
    body?: unknown,
    signal = AbortSignal.timeout(30_000),
  ) {
    try {
      return await fetch(new URL(path, this.root), {
        method,
        headers: {
          Authorization: `Bearer ${this.key}`,
          "Content-Type": "application/json",
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
        redirect: "error",
      });
    } catch (error) {
      const kind =
        error instanceof Error &&
        ["TimeoutError", "AbortError", "TypeError"].includes(error.name)
          ? error.name
          : "Error";
      throw new Error(`Notte transport failed (${kind})`);
    }
  }
  async close(id: string) {
    const deadline = AbortSignal.timeout(15_000);
    const stopped = await this.request(
      `/sessions/${id}/stop`,
      "DELETE",
      undefined,
      deadline,
    );
    await stopped.body?.cancel();
    if (!stopped.ok) throw new Error("Owned browser stop failed");
    while (!deadline.aborted) {
      const response = await this.request(
        `/sessions/${id}`,
        "GET",
        undefined,
        deadline,
      );
      if (!response.ok) {
        await response.body?.cancel();
        throw new Error("Owned browser status failed");
      }
      if ((await response.json()).status === "closed") return;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error("Owned browser did not close");
  }
  async owned<T>(
    options: object,
    work: (id: string, cdp: () => Promise<string>) => Promise<T>,
    trust = true,
  ) {
    // Keep the bounded start request independent of caller cancellation so its ID can be recovered.
    const response = await this.request(
      "/sessions/start",
      "POST",
      options,
      AbortSignal.timeout(60_000),
    );
    let value: { session_id?: unknown; cdp_url?: unknown };
    try {
      value = await response.json();
    } catch {
      throw new Error("Invalid Notte start response");
    }
    if (!sessionId(value.session_id))
      throw new Error(
        `Notte start returned no owned ID (HTTP ${response.status})`,
      );
    const id = value.session_id;
    try {
      if (!response.ok)
        throw new Error(`Notte start failed (HTTP ${response.status})`);
      if (
        trust &&
        (response.headers.get("X-Notte-Browser-Trust-Profile") !==
          "evervault" ||
          response.headers.get("X-Notte-Browser-Trust-SHA256") !== CA_SHA256)
      ) {
        throw new Error("Evervault browser trust was not verified");
      }
      return await work(id, async () => {
        let url = value.cdp_url;
        if (!url) {
          const debug = await this.request(`/sessions/${id}/debug`);
          if (!debug.ok) {
            await debug.body?.cancel();
            throw new Error("Notte CDP lookup failed");
          }
          url = (await debug.json()).ws?.cdp;
        }
        if (
          typeof url !== "string" ||
          !["ws:", "wss:"].includes(new URL(url).protocol)
        )
          throw new Error("Invalid Notte CDP response");
        return url;
      });
    } finally {
      await this.close(id);
    }
  }
}

export async function createToken(
  appId: string,
  apiKey: string,
  encrypted: string,
  target: URL,
  endpoint = "https://api.evervault.com/browser-tokens",
  signal?: AbortSignal,
) {
  if (
    !encrypted.startsWith("ev:") ||
    target.protocol !== "https:" ||
    target.username ||
    target.password ||
    target.hostname.includes("*")
  )
    throw new Error("Use an encrypted value and an exact HTTPS destination");
  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      redirect: "error",
      signal: AbortSignal.any([
        AbortSignal.timeout(30_000),
        ...(signal ? [signal] : []),
      ]),
      headers: {
        Authorization: `Basic ${Buffer.from(`${appId}:${apiKey}`).toString("base64")}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        data: [
          {
            category: "credential.password",
            value: encrypted,
            id: "login-password",
          },
        ],
        ttl: 300,
        permissions: [{ action: "decrypt", target: target.hostname }],
      }),
    });
  } catch {
    throw new Error("Evervault transport failed");
  }
  if (!response.ok) {
    await response.body?.cancel();
    throw new Error(`Evervault returned HTTP ${response.status}`);
  }
  try {
    const result = await response.json();
    const tokens = result.data.filter(
      (item: { id: string; category: string }) =>
        item.id === "login-password" && item.category === "credential.password",
    );
    const proxy = result.proxyConfiguration;
    if (
      tokens.length !== 1 ||
      typeof tokens[0].value !== "string" ||
      !tokens[0].value ||
      ![
        "us-va.browser.relay.evervault.app",
        "eu-ie.browser.relay.evervault.app",
      ].includes(proxy.hostname) ||
      !Number.isInteger(proxy.port) ||
      proxy.port < 1 ||
      proxy.port > 65535 ||
      typeof proxy.username !== "string" ||
      !proxy.username ||
      typeof proxy.password !== "string" || // pragma: allowlist secret (response type check)
      !proxy.password ||
      !(Date.parse(result.expiresAt) > Date.now())
    )
      throw new Error();
    return {
      token: tokens[0].value as string,
      proxy: {
        type: "external",
        server: `https://${proxy.hostname}:${proxy.port}`,
        username: proxy.username,
        password: proxy.password,
      } as Proxy,
    };
  } catch {
    throw new Error("Invalid Evervault token response");
  }
}

export async function disconnect(browser: Browser) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      browser.close(),
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(
          () => reject(new Error("Browser disconnect timed out")),
          3_000,
        );
      }),
    ]);
  } catch {
    throw new Error("Browser disconnect failed");
  } finally {
    clearTimeout(timer);
  }
}

export async function fillPassword(
  notte: Notte,
  proxy: Proxy,
  token: string,
  target: URL,
  signal?: AbortSignal,
  connect: Connect = (url) => chromium.connectOverCDP(url, { timeout: 30_000 }),
) {
  signal?.throwIfAborted();
  return notte.owned(
    {
      max_duration_minutes: 3,
      proxies: [proxy],
      browser_trust_profile: "evervault",
    },
    async (id, cdp) => {
      signal?.throwIfAborted();
      let browser: Browser | undefined;
      const abort = () => {
        if (browser) void disconnect(browser).catch(() => {});
      };
      try {
        browser = await connect(await cdp()); // Never forward the Notte API Authorization header to CDP.
        signal?.addEventListener("abort", abort, { once: true });
        signal?.throwIfAborted();
        const page = await (
          browser.contexts()[0] ?? (await browser.newContext())
        ).newPage();
        await page.goto(target.href, {
          waitUntil: "domcontentloaded",
          timeout: 30_000,
        });
        if (new URL(page.url()).origin !== target.origin)
          throw new Error("Destination redirected outside its origin");
        await page
          .locator('input[name="password"]')
          .fill(token, { timeout: 15_000 });
        return { session_id: id, filled: true };
      } catch {
        throw new Error("Browser token form fill failed");
      } finally {
        signal?.removeEventListener("abort", abort);
        if (browser) await disconnect(browser);
      }
    },
  );
}

export async function main(tokenize = createToken) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  process.once("SIGINT", abort);
  process.once("SIGTERM", abort);
  try {
    const required = (name: string) => {
      const value = process.env[name];
      if (!value) throw new Error(`Set ${name}`);
      return value;
    };
    const target = new URL(required("EVERVAULT_FORM_URL"));
    const { token, proxy } = await tokenize(
      required("EVERVAULT_APP_ID"),
      required("EVERVAULT_API_KEY"),
      required("EVERVAULT_ENCRYPTED_PASSWORD"),
      target,
      undefined,
      controller.signal,
    );
    controller.signal.throwIfAborted();
    await fillPassword(
      new Notte(required("NOTTE_API_KEY"), process.env.NOTTE_API_URL),
      proxy,
      token,
      target,
      controller.signal,
    );
    console.log("Token filled; owned browser closed.");
  } finally {
    process.removeListener("SIGINT", abort);
    process.removeListener("SIGTERM", abort);
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  main().catch(() => {
    console.error("Browser Tokens task failed.");
    process.exitCode = 1;
  });
