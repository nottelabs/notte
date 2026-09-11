import { vi } from 'vitest';
import type { NotteClient } from '@/client';
import type { ApiExecutionResponse, SerializedError, SessionResponse } from '@/lib/client/types.gen';

/** A `NotteClient` stand-in exposing only what `Session` reads. */
export function mockNotteClient(): NotteClient {
  return {
    getClient: vi.fn(() => ({})),
    withDbPreview: vi.fn((url: string) => url),
    getConfig: vi.fn(() => ({ baseUrl: 'https://api.notte.cc', timeoutMs: 60_000, verbose: false })),
  } as unknown as NotteClient;
}

export function sessionResponse(overrides: Partial<SessionResponse> = {}): SessionResponse {
  const now = new Date().toISOString();
  return {
    session_id: 'session-123',
    idle_timeout_minutes: 1,
    timeout_minutes: 1,
    created_at: now,
    last_accessed_at: now,
    status: 'active',
    ...overrides,
  };
}

/** The `ApiExecutionResponse` the API builds after an action ran. */
export function executionResult(overrides: Partial<ApiExecutionResponse> = {}): ApiExecutionResponse {
  const now = new Date().toISOString();
  return {
    action: { type: 'goto', url: 'https://example.com' },
    success: true,
    message: 'ok',
    data: null,
    exception: null,
    exception_detail: null,
    started_at: now,
    ended_at: now,
    ...overrides,
  };
}

export function serializedError(overrides: Partial<SerializedError> = {}): SerializedError {
  return {
    error_type: 'ActionExecutionError',
    dev_message: 'boom',
    user_message: 'boom',
    agent_message: 'boom',
    should_retry_later: false,
    should_notify_team: false,
    ...overrides,
  };
}

/** Serialise server side and rebuild client side, like the real API round trip. */
export function overTheWire<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}
