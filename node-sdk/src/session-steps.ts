import type { NotteClient } from '@/client';
import type { SessionResponse } from '@/lib/client/types.gen';

/** One step of a session, with the shape of an item of `SessionResponse.steps`. */
export type SessionStep = NonNullable<SessionResponse['steps']>[number];

/** One page of a session's steps, from `GET /sessions/{session_id}/steps`. */
export interface SessionStepsResponse {
  /** Steps of the session, in order. */
  steps: SessionStep[];
  /** Cursor of the next page, passed back as is; `null` on the last page. */
  next_cursor: string | null;
}

export interface SessionStepsOptions {
  /**
   * Opaque cursor from a previous page's `next_cursor`. Omit it for the first page.
   * A `NotteAPIError` with status 400 means it is no longer valid: restart from the first page.
   */
  cursor?: string;
  /** Maximum number of steps in the page; the API's default when omitted. */
  limit?: number;
}

export interface SessionStepsIterOptions {
  /** Maximum number of steps per page; the API's default when omitted. */
  limit?: number;
}

// Absent from the committed OpenAPI snapshot until the API publishes it.
export async function getSessionSteps(
  client: NotteClient,
  sessionId: string,
  options: SessionStepsOptions = {},
): Promise<SessionStepsResponse> {
  const response = await client.getClient().get<{ 200: Partial<SessionStepsResponse> }, unknown, true>({
    url: `/sessions/${encodeURIComponent(sessionId)}/steps`,
    query: { cursor: options.cursor, limit: options.limit },
    throwOnError: true,
  });
  return { steps: response.data.steps ?? [], next_cursor: response.data.next_cursor ?? null };
}

/**
 * Follow `next_cursor` page by page. A cursor that is no longer valid stops the
 * iteration with the 400 `NotteAPIError`, after the steps already yielded; it is
 * not restarted here, since that would yield those steps again.
 */
export async function* iterSessionSteps(
  client: NotteClient,
  sessionId: string,
  options: SessionStepsIterOptions = {},
): AsyncGenerator<SessionStep, void, undefined> {
  let cursor: string | undefined;
  while (true) {
    const page = await getSessionSteps(client, sessionId, { cursor, limit: options.limit });
    yield* page.steps;
    if (page.next_cursor === null) return;
    cursor = page.next_cursor;
  }
}
