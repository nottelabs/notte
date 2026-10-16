import { pathToFileURL } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { CallToolResultSchema } from '@modelcontextprotocol/sdk/types.js';

export async function withBrowser<T>(run: (call: (name: string, args: Record<string, unknown>) => Promise<any>, browserId: string) => Promise<T>) {
  const token = process.env.NOTTE_API_KEY;
  if (!token) throw new Error('Set NOTTE_API_KEY');
  const client = new Client({ name: 'notte-sandboxes-example', version: '1.0.0' });
  async function call(name: string, args: Record<string, unknown>) {
    const result = CallToolResultSchema.parse(await client.callTool({ name, arguments: args }));
    if (result.isError) throw new Error(`Notte MCP tool failed: ${name}`);
    const data = result.structuredContent ?? JSON.parse(result.content.filter(item => item.type === 'text').map(item => item.text).join('\n'));
    if (data.success === false) throw new Error(`Notte MCP tool failed: ${name}`);
    return data;
  }
  try {
    await client.connect(new StreamableHTTPClientTransport(new URL('/mcp', process.env.NOTTE_API_URL ?? 'https://api.notte.cc'), {
      requestInit: { headers: { Authorization: `Bearer ${token}` } },
    }));
    const tools = await client.listTools();
    for (const name of ['manage_browsers', 'browser_action', 'browser_observe']) {
      if (!tools.tools.some(tool => tool.name === name)) throw new Error('Required browser tool is unavailable');
    }
    const started = await call('manage_browsers', { action: 'start', max_duration_minutes: 3, idle_timeout_minutes: 1, use_proxy: false });
    if (typeof started.browser_id !== 'string') throw new Error('Browser start returned no ID');
    const browserId = started.browser_id as string;
    try { return await run(call, browserId); }
    finally { await call('manage_browsers', { action: 'stop', browser_id: browserId }); }
  } catch {
    throw new Error('Notte MCP browser task failed');
  } finally {
    try { await client.close(); }
    catch { throw new Error('Notte MCP connection cleanup failed'); }
  }
}

export async function main() {
  return withBrowser(async (call, browserId) => {
    await call('browser_action', { browser_id: browserId, action: { type: 'goto', url: 'https://example.com' } });
    const observed = await call('browser_observe', { browser_id: browserId, perception_type: 'fast' });
    return { title: observed.metadata.title as string, browser_id: browserId };
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) console.log(await main());
