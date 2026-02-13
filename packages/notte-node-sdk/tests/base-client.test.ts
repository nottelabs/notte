import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { BaseClient, type BaseClientOptions } from "../src/base-client.js";
import { AuthenticationError, NotteAPIError } from "../src/errors.js";
import { z } from "zod";

// Concrete subclass for testing the abstract BaseClient
class TestClient extends BaseClient {
  constructor(options: BaseClientOptions = {}) {
    super("test", options);
  }

  // Expose protected methods for testing
  public testGetHeaders() {
    return this.getHeaders();
  }
  public testBuildUrl(path: string) {
    return this.buildUrl(path);
  }
  public testRequest<T>(endpoint: Parameters<BaseClient["request"]>[0]) {
    return this.request(endpoint);
  }
  public testRequestList<T>(endpoint: Parameters<BaseClient["requestList"]>[0]) {
    return this.requestList(endpoint);
  }
}

describe("BaseClient", () => {
  const originalEnv = process.env.NOTTE_API_KEY;

  beforeEach(() => {
    process.env.NOTTE_API_KEY = "test-key";
  });

  afterEach(() => {
    if (originalEnv !== undefined) {
      process.env.NOTTE_API_KEY = originalEnv;
    } else {
      delete process.env.NOTTE_API_KEY;
    }
    vi.restoreAllMocks();
  });

  describe("constructor", () => {
    it("throws AuthenticationError when no API key", () => {
      delete process.env.NOTTE_API_KEY;
      expect(() => new TestClient()).toThrow(AuthenticationError);
    });

    it("reads API key from env", () => {
      const client = new TestClient();
      expect(client.apiKey).toBe("test-key");
    });

    it("prefers explicit API key over env", () => {
      const client = new TestClient({ apiKey: "explicit-key" });
      expect(client.apiKey).toBe("explicit-key");
    });

    it("uses default server URL", () => {
      const client = new TestClient();
      expect(client.serverUrl).toBe("https://api.notte.cc");
    });

    it("accepts custom server URL", () => {
      const client = new TestClient({ serverUrl: "https://custom.api" });
      expect(client.serverUrl).toBe("https://custom.api");
    });
  });

  describe("getHeaders", () => {
    it("includes Authorization and SDK headers", () => {
      const client = new TestClient({ apiKey: "my-key" });
      const headers = client.testGetHeaders();
      expect(headers.Authorization).toBe("Bearer my-key");
      expect(headers["x-notte-sdk-version"]).toBeDefined();
      expect(headers["x-notte-request-origin"]).toBe("sdk");
      expect(headers["Content-Type"]).toBe("application/json");
    });
  });

  describe("buildUrl", () => {
    it("combines server, base path, and endpoint", () => {
      const client = new TestClient({ apiKey: "k" });
      expect(client.testBuildUrl("foo")).toBe("https://api.notte.cc/test/foo");
    });

    it("handles empty endpoint path", () => {
      const client = new TestClient({ apiKey: "k" });
      expect(client.testBuildUrl("")).toBe("https://api.notte.cc/test");
    });

    it("strips duplicate slashes", () => {
      const client = new TestClient({
        apiKey: "k",
        serverUrl: "https://api.notte.cc/",
      });
      expect(client.testBuildUrl("/foo")).toBe("https://api.notte.cc/test/foo");
    });
  });

  describe("request", () => {
    it("parses response through Zod schema", async () => {
      const schema = z.object({ value: z.number() });
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(JSON.stringify({ value: 42 }), { status: 200 }),
      );

      const client = new TestClient({ apiKey: "k" });
      const result = await client.testRequest({
        path: "endpoint",
        method: "GET",
        responseSchema: schema,
      });
      expect(result).toEqual({ value: 42 });
    });

    it("throws NotteAPIError on non-OK response", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }),
      );

      const client = new TestClient({ apiKey: "k" });
      await expect(
        client.testRequest({
          path: "missing",
          method: "GET",
          responseSchema: z.object({}),
        }),
      ).rejects.toThrow(NotteAPIError);
    });

    it("throws on Zod validation failure", async () => {
      const schema = z.object({ value: z.number() });
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(JSON.stringify({ value: "not-a-number" }), { status: 200 }),
      );

      const client = new TestClient({ apiKey: "k" });
      await expect(
        client.testRequest({
          path: "bad",
          method: "GET",
          responseSchema: schema,
        }),
      ).rejects.toThrow();
    });
  });

  describe("requestList", () => {
    it("handles array response", async () => {
      const schema = z.object({ id: z.number() });
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(JSON.stringify([{ id: 1 }, { id: 2 }]), { status: 200 }),
      );

      const client = new TestClient({ apiKey: "k" });
      const result = await client.testRequestList({
        path: "list",
        method: "GET",
        responseSchema: schema,
      });
      expect(result).toEqual([{ id: 1 }, { id: 2 }]);
    });

    it("handles { items: [...] } response", async () => {
      const schema = z.object({ id: z.number() });
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(
          JSON.stringify({ items: [{ id: 3 }], page: 1 }),
          { status: 200 },
        ),
      );

      const client = new TestClient({ apiKey: "k" });
      const result = await client.testRequestList({
        path: "list",
        method: "GET",
        responseSchema: schema,
      });
      expect(result).toEqual([{ id: 3 }]);
    });
  });

  describe("healthCheck", () => {
    it("succeeds on 200", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response("ok", { status: 200 }),
      );
      const client = new TestClient({ apiKey: "k" });
      await expect(client.healthCheck()).resolves.toBeUndefined();
    });

    it("throws on non-200", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response("fail", { status: 503 }),
      );
      const client = new TestClient({ apiKey: "k" });
      await expect(client.healthCheck()).rejects.toThrow(NotteAPIError);
    });
  });
});
