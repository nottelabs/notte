/** `session.page()` retry against a local server, with the real playwright-core and its real errors. */
import net from 'node:net';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { Session } from '@/session';
import { sessionStart, sessionStatus } from '@/lib/client/sdk.gen';
import { mockNotteClient, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStatus: vi.fn(),
}));

const FORBIDDEN = 'HTTP/1.1 403 Forbidden\r\nContent-Length: 19\r\nConnection: close\r\n\r\nSession URL expired';

/** A server that hangs up the first `hangUps` upgrade requests and answers the next ones with a 403. */
async function server(hangUps: number): Promise<{ url: string; connections: () => number; close: () => void }> {
  let connections = 0;
  const srv = net.createServer(socket => {
    const index = connections++;
    socket.once('data', () => (index < hangUps ? socket.destroy() : socket.end(FORBIDDEN)));
  });
  await new Promise<void>(resolve => srv.listen(0, '127.0.0.1', resolve));
  const { port } = srv.address() as net.AddressInfo;
  return { url: `ws://127.0.0.1:${port}/s/token`, connections: () => connections, close: () => srv.close() };
}

describe('session.page() CDP connection retry with playwright-core', () => {
  let close = () => {};

  beforeEach(() => {
    vi.resetAllMocks();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(sessionStatus).mockRejectedValue(new Error('status unavailable'));
  });

  afterEach(() => close());

  it.each([
    ['a hang-up is retried once', 1, 2],
    ['a 403 is not retried', 0, 1],
    ['a second hang-up is not retried', 2, 2],
  ])('%s', async (_name, hangUps, attempts) => {
    const local = await server(hangUps);
    close = local.close;
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: local.url }) } as never);
    const session = new Session(mockNotteClient());
    await session.start();

    const error = await session.page().catch((e: unknown) => e);

    expect(local.connections()).toBe(attempts);
    const reason = attempts > hangUps ? '403 Forbidden' : 'socket hang up';
    expect((error as Error).message.split('\n')[0]).toContain(reason);
  });
});
