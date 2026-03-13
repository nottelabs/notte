import { describe, it, expect } from "vitest";
import {
  SessionStartRequestSchema,
  SessionResponseSchema,
  SessionListRequestSchema,
  ScrapeRequestSchema,
  ObserveRequestSchema,
  ExecutionRequestSchema,
  CookieSchema,
  SetCookiesRequestSchema,
  GetCookiesResponseSchema,
} from "../src/types/index.js";

describe("SessionStartRequestSchema", () => {
  it("accepts empty object", () => {
    expect(() => SessionStartRequestSchema.parse({})).not.toThrow();
  });

  it("accepts valid fields", () => {
    const result = SessionStartRequestSchema.parse({
      headless: true,
      max_duration_minutes: 10,
      idle_timeout_minutes: 3,
    });
    expect(result.headless).toBe(true);
  });

  it("rejects unknown fields (strict)", () => {
    expect(() =>
      SessionStartRequestSchema.parse({ unknown_field: true }),
    ).toThrow();
  });
});

describe("SessionResponseSchema", () => {
  const validResponse = {
    session_id: "sess-1",
    idle_timeout_minutes: 3,
    max_duration_minutes: 15,
    created_at: "2024-01-01T00:00:00Z",
    last_accessed_at: "2024-01-01T00:00:00Z",
    status: "active",
  };

  it("parses a valid response", () => {
    const result = SessionResponseSchema.parse(validResponse);
    expect(result.session_id).toBe("sess-1");
    expect(result.status).toBe("active");
  });

  it("allows extra fields (passthrough)", () => {
    const result = SessionResponseSchema.parse({
      ...validResponse,
      some_future_field: "value",
    });
    expect((result as Record<string, unknown>).some_future_field).toBe("value");
  });

  it("rejects invalid status", () => {
    expect(() =>
      SessionResponseSchema.parse({ ...validResponse, status: "invalid" }),
    ).toThrow();
  });
});

describe("SessionListRequestSchema", () => {
  it("accepts empty object", () => {
    expect(() => SessionListRequestSchema.parse({})).not.toThrow();
  });

  it("accepts valid params", () => {
    const result = SessionListRequestSchema.parse({
      only_active: false,
      page: 2,
      page_size: 20,
    });
    expect(result.page).toBe(2);
  });
});

describe("ScrapeRequestSchema", () => {
  it("accepts empty object", () => {
    expect(() => ScrapeRequestSchema.parse({})).not.toThrow();
  });

  it("accepts scrape params", () => {
    const result = ScrapeRequestSchema.parse({
      only_main_content: true,
      scrape_links: false,
    });
    expect(result.only_main_content).toBe(true);
  });

  it("rejects unknown fields", () => {
    expect(() =>
      ScrapeRequestSchema.parse({ bogus: true }),
    ).toThrow();
  });
});

describe("ObserveRequestSchema", () => {
  it("accepts instructions", () => {
    const result = ObserveRequestSchema.parse({
      instructions: "Find the login button",
    });
    expect(result.instructions).toBe("Find the login button");
  });
});

describe("ExecutionRequestSchema", () => {
  it("requires type field", () => {
    expect(() => ExecutionRequestSchema.parse({})).toThrow();
  });

  it("accepts goto action", () => {
    const result = ExecutionRequestSchema.parse({
      type: "goto",
      url: "https://example.com",
    });
    expect(result.type).toBe("goto");
  });

  it("accepts click action with id", () => {
    const result = ExecutionRequestSchema.parse({
      type: "click",
      id: "B1",
    });
    expect(result.type).toBe("click");
    expect(result.id).toBe("B1");
  });
});

describe("CookieSchema", () => {
  const validCookie = {
    name: "session",
    value: "abc123",
    domain: ".example.com",
    path: "/",
    httpOnly: true,
  };

  it("parses valid cookie", () => {
    const result = CookieSchema.parse(validCookie);
    expect(result.name).toBe("session");
  });

  it("allows extra fields (passthrough)", () => {
    const result = CookieSchema.parse({ ...validCookie, custom: "field" });
    expect((result as Record<string, unknown>).custom).toBe("field");
  });

  it("requires mandatory fields", () => {
    expect(() => CookieSchema.parse({ name: "x" })).toThrow();
  });
});

describe("SetCookiesRequestSchema", () => {
  it("requires cookies array", () => {
    expect(() => SetCookiesRequestSchema.parse({})).toThrow();
  });

  it("accepts valid cookies", () => {
    const result = SetCookiesRequestSchema.parse({
      cookies: [
        {
          name: "a",
          value: "b",
          domain: ".test.com",
          path: "/",
          httpOnly: false,
        },
      ],
    });
    expect(result.cookies).toHaveLength(1);
  });
});

describe("GetCookiesResponseSchema", () => {
  it("parses response with cookies", () => {
    const result = GetCookiesResponseSchema.parse({
      cookies: [
        {
          name: "a",
          value: "b",
          domain: ".test.com",
          path: "/",
          httpOnly: false,
        },
      ],
    });
    expect(result.cookies).toHaveLength(1);
  });
});
