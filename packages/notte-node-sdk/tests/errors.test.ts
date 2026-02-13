import { describe, it, expect } from "vitest";
import {
  NotteAPIError,
  AuthenticationError,
  InvalidRequestError,
} from "../src/errors.js";

describe("NotteAPIError", () => {
  it("stores statusCode, errorBody, and path", () => {
    const err = new NotteAPIError(404, { detail: "Not found" }, "/sessions/abc");
    expect(err.statusCode).toBe(404);
    expect(err.errorBody).toEqual({ detail: "Not found" });
    expect(err.path).toBe("/sessions/abc");
    expect(err.name).toBe("NotteAPIError");
  });

  it("extracts message from detail field", () => {
    const err = new NotteAPIError(400, { detail: "Bad request" }, "/test");
    expect(err.message).toContain("Bad request");
  });

  it("extracts message from message field", () => {
    const err = new NotteAPIError(500, { message: "Internal error" }, "/test");
    expect(err.message).toContain("Internal error");
  });

  it("falls back to generic message", () => {
    const err = new NotteAPIError(503, "plain text", "/test");
    expect(err.message).toContain("503");
  });
});

describe("AuthenticationError", () => {
  it("has default message", () => {
    const err = new AuthenticationError();
    expect(err.message).toContain("NOTTE_API_KEY");
    expect(err.name).toBe("AuthenticationError");
  });

  it("accepts custom message", () => {
    const err = new AuthenticationError("Custom msg");
    expect(err.message).toBe("Custom msg");
  });
});

describe("InvalidRequestError", () => {
  it("stores message", () => {
    const err = new InvalidRequestError("bad param");
    expect(err.message).toBe("bad param");
    expect(err.name).toBe("InvalidRequestError");
  });
});
