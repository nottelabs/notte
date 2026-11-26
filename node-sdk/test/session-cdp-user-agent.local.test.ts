/** `session.page()` sends the SDK's User-Agent on the CDP WebSocket upgrade, with the real playwright-core. Mirrors `tests/sdk/test_session_cdp_user_agent.py`. */
import net from 'node:net';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { Session, cdpHeaders, onApiOrigin } from '@/session';
import type { NotteClient } from '@/client';
import { sessionStart, sessionStatus } from '@/lib/client/sdk.gen';
import { clientUserAgent } from '@/client-info';
import { REQUEST_ORIGIN } from '@/client';
import { SDK_VERSION } from '@/version';
import { mockNotteClient, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStatus: vi.fn(),
}));

const FORBIDDEN = 'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n';

/** A server that records each WebSocket upgrade request's headers and answers 403. */
async function server(): Promise<{ url: string; upgrades: Array<Record<string, string>>; close: () => void }> {
  const upgrades: Array<Record<string, string>> = [];
  const srv = net.createServer(socket => {
    let request = '';
    socket.on('data', chunk => {
      request += chunk.toString();
      const end = request.indexOf('\r\n\r\n');
      if (end < 0) return;
      const headers: Record<string, string> = {};
      for (const line of request.slice(0, end).split('\r\n').slice(1)) {
        const colon = line.indexOf(':');
        headers[line.slice(0, colon).trim().toLowerCase()] = line.slice(colon + 1).trim();
      }
      upgrades.push(headers);
      socket.end(FORBIDDEN);
    });
  });
  await new Promise<void>(resolve => srv.listen(0, '127.0.0.1', resolve));
  const { port } = srv.address() as net.AddressInfo;
  return { url: `ws://127.0.0.1:${port}/sessions/s/cdp`, upgrades, close: () => srv.close() };
}

/** A client whose API is at `baseUrl`. */
function clientAt(baseUrl: string): NotteClient {
  const client = mockNotteClient();
  vi.mocked(client.getConfig).mockReturnValue({ baseUrl } as ReturnType<NotteClient['getConfig']>);
  return client;
}

/** The http(s) API origin a ws(s) CDP url lives on. */
function apiOf(cdpUrl: string): string {
  const url = new URL(cdpUrl);
  return `${url.protocol === 'wss:' ? 'https' : 'http'}://${url.host}`;
}

describe('session.page() User-Agent with playwright-core', () => {
  let close = () => {};

  beforeEach(() => {
    vi.resetAllMocks();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(sessionStatus).mockRejectedValue(new Error('status unavailable'));
    vi.stubEnv('GITHUB_ACTIONS', 'true');
    vi.stubEnv('GITHUB_REPOSITORY', 'acme/shop');
    vi.stubEnv('GITHUB_RUN_ID', '');
    vi.stubEnv('GITHUB_RUN_ATTEMPT', '');
    vi.stubEnv('GITHUB_JOB', 'e2e');
  });

  afterEach(() => {
    close();
    vi.unstubAllEnvs();
  });

  it('the CDP headers name the SDK and its GitHub Actions job on the API origin', () => {
    expect(cdpHeaders('wss://api.notte.cc/cdp', 'https://api.notte.cc')).toEqual({
      'user-agent': clientUserAgent(),
      'x-notte-request-origin': REQUEST_ORIGIN,
      'x-notte-sdk-version': SDK_VERSION,
    });
    expect(cdpHeaders('wss://api.notte.cc/cdp', 'https://api.notte.cc')['user-agent']).toMatch(
      / github-actions \(repo=acme\/shop; job=e2e\)$/,
    );
  });

  it('keeps the User-Agent, and its CI job, off any other origin', () => {
    expect(onApiOrigin('wss://api.notte.cc:443/cdp', 'https://api.notte.cc')).toBe(true);
    expect(onApiOrigin('ws://localhost:8000/cdp', 'http://localhost:8000')).toBe(true);
    expect(onApiOrigin('wss://cdp.example.com/cdp', 'https://api.notte.cc')).toBe(false);
    expect(onApiOrigin('ws://api.notte.cc/cdp', 'https://api.notte.cc')).toBe(false);
    expect(onApiOrigin('wss://api.notte.cc:8443/cdp', 'https://api.notte.cc')).toBe(false);
    expect(onApiOrigin('wss://api.notte.cc/cdp', '/api/notte')).toBe(false);
    expect(cdpHeaders('wss://cdp.example.com/cdp', 'https://api.notte.cc')).toEqual({
      'x-notte-request-origin': REQUEST_ORIGIN,
      'x-notte-sdk-version': SDK_VERSION,
    });
  });

  it("replaces Playwright's own User-Agent on Notte's CDP endpoint", async () => {
    const local = await server();
    close = local.close;
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: local.url }) } as never);
    const session = new Session(clientAt(apiOf(local.url)));
    await session.start();

    const error = await session.page().catch((e: unknown) => e);

    expect((error as Error).message).toContain('403 Forbidden');
    expect(local.upgrades).toHaveLength(1);
    expect(local.upgrades[0]['user-agent']).toBe(clientUserAgent());
    expect(local.upgrades[0]['x-notte-request-origin']).toBe(REQUEST_ORIGIN);
  });

  it("keeps Playwright's User-Agent on an API-returned CDP url on another origin", async () => {
    const local = await server();
    close = local.close;
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: local.url }) } as never);
    const session = new Session(clientAt('https://api.notte.cc'));
    await session.start();

    await session.page().catch(() => undefined);

    expect(local.upgrades).toHaveLength(1);
    expect(local.upgrades[0]['user-agent']).toMatch(/^Playwright\//);
    expect(local.upgrades[0]['x-notte-request-origin']).toBe(REQUEST_ORIGIN);
  });

  it("keeps Playwright's User-Agent on a caller's own browser", async () => {
    const local = await server();
    close = local.close;
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: local.url }) } as never);
    const session = new Session(mockNotteClient(), { cdp_url: local.url });
    await session.start();

    await session.page().catch(() => undefined);

    expect(local.upgrades).toHaveLength(1);
    expect(local.upgrades[0]['user-agent']).toMatch(/^Playwright\//);
    expect(local.upgrades[0]['x-notte-request-origin']).toBeUndefined();
  });
});
