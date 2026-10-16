import { pathToFileURL } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { NotteClient } from 'notte-sdk';

export type PipedreamConfig = {
  clientId: string; clientSecret: string; projectId: string; externalUserId: string; app?: string;
};
type Options = { providerFetch?: typeof fetch; pageUrl?: string; signal?: AbortSignal };

function toolData(result: unknown): unknown {
  const value = result as { isError?: boolean; structuredContent?: unknown; content: { type: string; text?: string }[] };
  if (value.isError) throw new Error('Browser tool failed');
  if (value.structuredContent !== undefined) return value.structuredContent;
  return JSON.parse(value.content.find((item) => item.type === 'text')!.text!);
}

export async function runDemo(config: PipedreamConfig, options: Options = {}) {
  const signal = AbortSignal.any([AbortSignal.timeout(90_000), ...(options.signal ? [options.signal] : [])]);
  const providerFetch = options.providerFetch ?? fetch;
  let sessionId = 'unallocated';
  try {
    return await new NotteClient().Session({ max_duration_minutes: 3 }).use(async (browser) => {
      sessionId = browser.getId()!;
      const notte = new Client({ name: 'notte-pipedream-browser', version: '1.0.0' });
      const pipedream = new Client({ name: 'notte-pipedream-discovery', version: '1.0.0' });
      let failed = false;
      try {
        const api = process.env.NOTTE_API_URL ?? 'https://api.notte.cc';
        await notte.connect(new StreamableHTTPClientTransport(new URL('/mcp', api), {
          requestInit: { headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY!}` }, signal, redirect: 'error' },
        }));
        const action = toolData(await notte.callTool({ name: 'browser_action', arguments: {
          browser_id: sessionId, action: { type: 'goto', url: options.pageUrl ?? 'https://example.com' },
        } }, undefined, { signal })) as { success?: boolean };
        if (action.success !== true) throw new Error('Browser navigation failed');
        const page = toolData(await notte.callTool({ name: 'browser_scrape', arguments: { browser_id: sessionId } }, undefined, { signal }));
        const response = await providerFetch('https://api.pipedream.com/v1/oauth/token', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, redirect: 'error', signal,
          body: JSON.stringify({ grant_type: 'client_credentials', client_id: config.clientId, client_secret: config.clientSecret }),
        });
        if (!response.ok) throw new Error(`Pipedream OAuth HTTP ${response.status}`);
        const { access_token: token } = await response.json() as { access_token: string };
        if (typeof token !== 'string' || !token) throw new Error('Pipedream OAuth returned no access token');
        await pipedream.connect(new StreamableHTTPClientTransport(new URL('https://remote.mcp.pipedream.net/v3'), {
          fetch: providerFetch,
          requestInit: { signal, redirect: 'error', headers: {
            Authorization: `Bearer ${token}`, 'x-pd-project-id': config.projectId,
            'x-pd-environment': 'development', 'x-pd-external-user-id': config.externalUserId,
            'x-pd-app-slug': config.app ?? 'github',
          } },
        }));
        const { tools } = await pipedream.listTools({}, { signal });
        return { session_id: sessionId, page, tool_names: tools.map((tool) => tool.name) };
      } catch {
        failed = true;
        // The SDK context logs exceptions during cleanup; keep provider errors out of it.
        throw new Error(`Pipedream discovery ${signal.aborted ? 'cancelled' : 'failed'} (session ${sessionId})`);
      } finally {
        const closed = await Promise.allSettled([pipedream.close(), notte.close()]);
        if (!failed && closed.some((item) => item.status === 'rejected')) throw new Error('MCP cleanup failed');
        if (!failed && signal.aborted) throw new Error(`Pipedream discovery cancelled (session ${sessionId})`);
      }
    });
  } catch {
    throw new Error(`Pipedream discovery ${signal.aborted ? 'cancelled' : 'failed'} (session ${sessionId})`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const required = (name: string) => {
    const value = process.env[name];
    if (!value) throw new Error(`Set ${name}`);
    return value;
  };
  const result = await runDemo({ clientId: required('PIPEDREAM_CLIENT_ID'), clientSecret: required('PIPEDREAM_CLIENT_SECRET'),
    projectId: required('PIPEDREAM_PROJECT_ID'), externalUserId: required('PIPEDREAM_EXTERNAL_USER_ID'), app: process.env.PIPEDREAM_APP });
  console.log(JSON.stringify({ session_id: result.session_id, tool_count: result.tool_names.length }));
}
