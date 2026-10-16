import type { BrowserProvider } from '@e2e-dev/web';
import { NotteClient } from 'notte-sdk';

function client(env: Readonly<Record<string, string | undefined>>) {
  if (!env.NOTTE_API_KEY) throw new Error('Set NOTTE_API_KEY for the Notte browser provider');
  return new NotteClient({
    apiKey: env.NOTTE_API_KEY, baseUrl: env.NOTTE_API_URL || 'https://api.notte.cc',
    timeoutMs: 30_000,
  });
}

export function notte(): BrowserProvider {
  return {
    name: 'notte',
    scope: 'attempt',
    async acquire(request) {
      request.signal.throwIfAborted();
      const session = client(request.env).Session({ max_duration_minutes: 3 });
      try {
        await session.start({ signal: request.signal });
        request.signal.throwIfAborted();
        const endpoint = await session.cdpUrl();
        request.signal.throwIfAborted();
        return { id: session.getId()!, cdpEndpoint: endpoint, reconnectEndpoint: endpoint };
      } catch {
        try {
          await session.stop();
        } catch {
          throw new Error(`Notte browser cleanup failed${session.getId() ? ` (session ${session.getId()})` : ''}`);
        }
        throw new Error(`Notte browser acquisition failed${session.getId() ? ` (session ${session.getId()})` : ''}`);
      }
    },
    async release(lease, context) {
      try {
        await client(context.env).sessions.stop(lease.id, undefined, { signal: context.signal });
      } catch {
        throw new Error(`Notte browser release failed (session ${lease.id})`);
      }
    },
  };
}
