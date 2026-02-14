import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SessionsClient } from "../src/sessions/sessions-client.js";

const MOCK_SESSION_RESPONSE = {
  session_id: "sess-123",
  idle_timeout_minutes: 3,
  max_duration_minutes: 15,
  created_at: "2024-01-01T00:00:00Z",
  last_accessed_at: "2024-01-01T00:00:00Z",
  status: "active" as const,
};

function mockFetch(body: unknown, status = 200) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("SessionsClient", () => {
  let client: SessionsClient;

  beforeEach(() => {
    client = new SessionsClient({ apiKey: "test-key" }); // pragma: allowlist secret
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("start", () => {
    it("sends POST to /sessions/start", async () => {
      const spy = mockFetch(MOCK_SESSION_RESPONSE);
      const result = await client.start();
      expect(result.session_id).toBe("sess-123");

      const [url, init] = spy.mock.calls[0];
      expect(url.toString()).toContain("/sessions/start");
      expect((init as RequestInit).method).toBe("POST");
    });

    it("sends request body when params provided", async () => {
      const spy = mockFetch(MOCK_SESSION_RESPONSE);
      await client.start({ headless: true, max_duration_minutes: 5 });

      const [, init] = spy.mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.headless).toBe(true);
      expect(body.max_duration_minutes).toBe(5);
    });
  });

  describe("stop", () => {
    it("sends DELETE to /sessions/{id}/stop", async () => {
      const spy = mockFetch({ ...MOCK_SESSION_RESPONSE, status: "closed" });
      const result = await client.stop("sess-123");
      expect(result.status).toBe("closed");

      const [url, init] = spy.mock.calls[0];
      expect(url.toString()).toContain("/sessions/sess-123/stop");
      expect((init as RequestInit).method).toBe("DELETE");
    });
  });

  describe("status", () => {
    it("sends GET to /sessions/{id}", async () => {
      const spy = mockFetch(MOCK_SESSION_RESPONSE);
      const result = await client.status("sess-123");
      expect(result.session_id).toBe("sess-123");

      const [url, init] = spy.mock.calls[0];
      expect(url.toString()).toContain("/sessions/sess-123");
      expect((init as RequestInit).method).toBe("GET");
    });
  });

  describe("list", () => {
    it("sends GET to /sessions/ and returns array", async () => {
      const spy = mockFetch([MOCK_SESSION_RESPONSE]);
      const result = await client.list();
      expect(result).toHaveLength(1);
      expect(result[0].session_id).toBe("sess-123");

      const [url, init] = spy.mock.calls[0];
      expect(url.toString()).toContain("/sessions");
      expect((init as RequestInit).method).toBe("GET");
    });

    it("passes query params", async () => {
      const spy = mockFetch([MOCK_SESSION_RESPONSE]);
      await client.list({ only_active: true, page: 2 });

      const [url] = spy.mock.calls[0];
      const parsedUrl = new URL(url.toString());
      expect(parsedUrl.searchParams.get("only_active")).toBe("true");
      expect(parsedUrl.searchParams.get("page")).toBe("2");
    });
  });

  describe("scrape", () => {
    it("sends POST to /sessions/{id}/page/scrape", async () => {
      const mockResponse = {
        session: MOCK_SESSION_RESPONSE,
        markdown: "# Hello",
      };
      const spy = mockFetch(mockResponse);
      const result = await client.scrape("sess-123");

      expect(result.session.session_id).toBe("sess-123");
      const [url, init] = spy.mock.calls[0];
      expect(url.toString()).toContain("/sessions/sess-123/page/scrape");
      expect((init as RequestInit).method).toBe("POST");
    });
  });

  describe("observe", () => {
    it("sends POST to /sessions/{id}/page/observe", async () => {
      const mockResponse = {
        session: MOCK_SESSION_RESPONSE,
        metadata: {},
      };
      const spy = mockFetch(mockResponse);
      const result = await client.observe("sess-123", {
        instructions: "Find buttons",
      });

      expect(result.session.session_id).toBe("sess-123");
      const [url, init] = spy.mock.calls[0];
      expect(url.toString()).toContain("/sessions/sess-123/page/observe");
      expect((init as RequestInit).method).toBe("POST");

      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.instructions).toBe("Find buttons");
    });
  });

  describe("execute", () => {
    it("sends POST to /sessions/{id}/page/execute", async () => {
      const mockResponse = {
        session: MOCK_SESSION_RESPONSE,
        success: true,
        message: "ok",
      };
      const spy = mockFetch(mockResponse);
      const result = await client.execute("sess-123", {
        type: "goto",
        url: "https://example.com",
      });

      expect(result.success).toBe(true);
      const [url, init] = spy.mock.calls[0];
      expect(url.toString()).toContain("/sessions/sess-123/page/execute");
      expect((init as RequestInit).method).toBe("POST");

      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.type).toBe("goto");
      expect(body.url).toBe("https://example.com");
    });
  });

  describe("setCookies", () => {
    it("sends POST to /sessions/{id}/cookies", async () => {
      const mockResponse = { success: true, message: "Cookies set" };
      const spy = mockFetch(mockResponse);
      const cookies = [
        {
          name: "session",
          value: "abc",
          domain: ".example.com",
          path: "/",
          httpOnly: true,
        },
      ];
      const result = await client.setCookies("sess-123", cookies);

      expect(result.success).toBe(true);
      const [url, init] = spy.mock.calls[0];
      expect(url.toString()).toContain("/sessions/sess-123/cookies");
      expect((init as RequestInit).method).toBe("POST");
    });
  });

  describe("getCookies", () => {
    it("sends GET to /sessions/{id}/cookies", async () => {
      const mockResponse = { cookies: [] };
      const spy = mockFetch(mockResponse);
      const result = await client.getCookies("sess-123");

      expect(result.cookies).toEqual([]);
      const [url, init] = spy.mock.calls[0];
      expect(url.toString()).toContain("/sessions/sess-123/cookies");
      expect((init as RequestInit).method).toBe("GET");
    });
  });
});
