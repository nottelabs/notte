import { type NotteClient, sessionStatus } from '@/index';

/** Stop acknowledges in-memory closure before background cleanup persists it. */
export async function expectSessionClosed(client: NotteClient, sessionId: string, example: string): Promise<void> {
  const timeout = 15_000;
  const interval = 500;
  const started = Date.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const observations: string[] = [];
  const failure = () => new Error(
    `${example}: session ${sessionId} did not become closed within ${timeout}ms; observed ${observations.join(', ') || 'no response'}`,
  );
  try {
    while (!controller.signal.aborted) {
      const response = await sessionStatus({
        client: client.getClient(),
        path: { session_id: sessionId },
        signal: controller.signal,
        throwOnError: true,
      });
      const status = response.data.status;
      observations.push(`${Date.now() - started}ms=${status}`);
      if (controller.signal.aborted) throw failure();
      if (status === 'closed') return;
      if (status !== 'active') {
        throw new Error(`${example}: session ${sessionId} returned unexpected status ${status}`);
      }
      const remaining = timeout - (Date.now() - started);
      if (remaining <= 0) break;
      await new Promise(resolve => setTimeout(resolve, Math.min(interval, remaining)));
    }
    throw failure();
  } catch (error) {
    if (controller.signal.aborted) throw failure();
    // Authentication, transport, and other API errors are not closure delays.
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
