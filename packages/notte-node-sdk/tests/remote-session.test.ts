import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { RemoteSession } from "../src/sessions/remote-session.js";
import { SessionsClient } from "../src/sessions/sessions-client.js";

const MOCK_SESSION_RESPONSE = {
  session_id: "sess-456",
  idle_timeout_minutes: 3,
  max_duration_minutes: 15,
  created_at: "2024-01-01T00:00:00Z",
  last_accessed_at: "2024-01-01T00:00:00Z",
  status: "active" as const,
};

const MOCK_STOPPED_RESPONSE = {
  ...MOCK_SESSION_RESPONSE,
  status: "closed" as const,
};

function mockFetchSequence(responses: unknown[]) {
  const spy = vi.spyOn(globalThis, "fetch");
  for (const body of responses) {
    spy.mockResolvedValueOnce(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  }
  return spy;
}

describe("RemoteSession", () => {
  let client: SessionsClient;

  beforeEach(() => {
    client = new SessionsClient({ apiKey: "test-key" });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws if sessionId accessed before start", () => {
    const session = new RemoteSession(client);
    expect(() => session.sessionId).toThrow("not been started");
  });

  it("start() sets sessionId", async () => {
    mockFetchSequence([MOCK_SESSION_RESPONSE]);
    const session = new RemoteSession(client);
    await session.start();
    expect(session.sessionId).toBe("sess-456");
    expect(session.isStarted).toBe(true);
  });

  it("start() throws if already started", async () => {
    mockFetchSequence([MOCK_SESSION_RESPONSE]);
    const session = new RemoteSession(client);
    await session.start();
    await expect(session.start()).rejects.toThrow("already started");
  });

  it("stop() marks as stopped", async () => {
    mockFetchSequence([MOCK_SESSION_RESPONSE, MOCK_STOPPED_RESPONSE]);
    const session = new RemoteSession(client);
    await session.start();
    await session.stop();
    expect(session.isStopped).toBe(true);
  });

  it("stop() is idempotent", async () => {
    mockFetchSequence([MOCK_SESSION_RESPONSE, MOCK_STOPPED_RESPONSE]);
    const session = new RemoteSession(client);
    await session.start();
    await session.stop();
    // Second call should not throw
    const result = await session.stop();
    expect(result.status).toBe("closed");
  });

  it("delegates scrape to client", async () => {
    const scrapeResponse = { session: MOCK_SESSION_RESPONSE, markdown: "# Hi" };
    mockFetchSequence([MOCK_SESSION_RESPONSE, scrapeResponse]);
    const session = new RemoteSession(client);
    await session.start();
    const result = await session.scrape();
    expect(result.markdown).toBe("# Hi");
  });

  it("delegates observe to client", async () => {
    const observeResponse = { session: MOCK_SESSION_RESPONSE, metadata: {} };
    mockFetchSequence([MOCK_SESSION_RESPONSE, observeResponse]);
    const session = new RemoteSession(client);
    await session.start();
    const result = await session.observe({ instructions: "Find links" });
    expect(result.session.session_id).toBe("sess-456");
  });

  it("delegates execute to client", async () => {
    const execResponse = {
      session: MOCK_SESSION_RESPONSE,
      success: true,
      message: "ok",
    };
    mockFetchSequence([MOCK_SESSION_RESPONSE, execResponse]);
    const session = new RemoteSession(client);
    await session.start();
    const result = await session.execute({ type: "goto", url: "https://example.com" });
    expect(result.success).toBe(true);
  });

  describe("RemoteSession.use()", () => {
    it("auto-starts and auto-stops", async () => {
      mockFetchSequence([
        MOCK_SESSION_RESPONSE,
        { session: MOCK_SESSION_RESPONSE, markdown: "data" },
        MOCK_STOPPED_RESPONSE,
      ]);

      const result = await RemoteSession.use(client, {}, async (session) => {
        const data = await session.scrape();
        return data.markdown;
      });
      expect(result).toBe("data");
    });

    it("stops even on error", async () => {
      const spy = mockFetchSequence([
        MOCK_SESSION_RESPONSE,
        MOCK_STOPPED_RESPONSE,
      ]);

      await expect(
        RemoteSession.use(client, {}, async () => {
          throw new Error("boom");
        }),
      ).rejects.toThrow("boom");

      // Should have called fetch twice: start + stop
      expect(spy).toHaveBeenCalledTimes(2);
    });
  });

  describe("RemoteSession.fromId()", () => {
    it("attaches to existing session without starting", () => {
      const session = RemoteSession.fromId(client, "existing-123");
      expect(session.sessionId).toBe("existing-123");
      expect(session.isStarted).toBe(true);
    });
  });
});
