import { pathToFileURL } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport, StreamableHTTPError } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { CallToolResultSchema, McpError } from '@modelcontextprotocol/sdk/types.js';

class TaskError extends Error {}
function failure(step: string, error: unknown) {
  if (error instanceof TaskError) return error;
  const code = error instanceof StreamableHTTPError ? `HTTP ${error.code}` : error instanceof McpError ? `MCP ${error.code}` : '';
  const detail = code || (error instanceof Error && error.name === 'TimeoutError' ? 'timeout' : '');
  // Provider messages and causes can contain credentials; retain only safe diagnostics.
  return new TaskError(`Notte MCP ${step} failed${detail ? ` (${detail})` : ''}`);
}

export async function withBrowser<T>(run: (call: (name: string, args: Record<string, unknown>) => Promise<any>, browserId: string) => Promise<T>) {
  const token = process.env.NOTTE_API_KEY;
  if (!token) throw new Error('Set NOTTE_API_KEY');
  const client = new Client({ name: 'notte-sandboxes-example', version: '1.0.0' });
  async function call(name: string, args: Record<string, unknown>) {
    try {
      const result = CallToolResultSchema.parse(await client.callTool({ name, arguments: args }));
      if (result.isError) throw new Error();
      const data = result.structuredContent ?? JSON.parse(result.content.filter(item => item.type === 'text').map(item => item.text).join('\n'));
      if (data.success === false) throw new Error();
      return data;
    } catch (error) { throw failure(`tool ${name}`, error); }
  }
  let browserId: string | undefined;
  let result: T | undefined;
  let step = 'connection';
  const failures: Error[] = [];
  try {
    await client.connect(new StreamableHTTPClientTransport(new URL('/mcp', process.env.NOTTE_API_URL ?? 'https://api.notte.cc'), {
      requestInit: { headers: { Authorization: `Bearer ${token}` } },
    }));
    step = 'tool discovery';
    const tools = await client.listTools();
    for (const name of ['manage_browsers', 'browser_action', 'browser_observe']) {
      if (!tools.tools.some(tool => tool.name === name)) throw new TaskError(`Required Notte MCP tool is unavailable: ${name}`);
    }
    const started = await call('manage_browsers', { action: 'start', max_duration_minutes: 3, idle_timeout_minutes: 1, use_proxy: false });
    if (typeof started.browser_id !== 'string') throw new TaskError('Notte MCP browser start returned no ID');
    browserId = started.browser_id as string;
    step = 'browser task';
    result = await run(call, browserId);
  } catch (error) { failures.push(failure(step, error)); }
  finally {
    if (browserId) {
      try { await call('manage_browsers', { action: 'stop', browser_id: browserId }); }
      catch (error) { failures.push(new TaskError('Notte MCP browser stop failed', { cause: failure('browser stop', error) })); }
    }
    try { await client.close(); }
    catch (error) { failures.push(failure('connection cleanup', error)); }
  }
  if (failures.length > 1) throw new AggregateError(failures, 'Notte MCP task and cleanup failed');
  if (failures.length) throw failures[0];
  return result as T;
}

export async function main() {
  return withBrowser(async (call, browserId) => {
    await call('browser_action', { browser_id: browserId, action: { type: 'goto', url: 'https://example.com' } });
    const observed = await call('browser_observe', { browser_id: browserId, perception_type: 'fast' });
    return { title: observed.metadata.title as string, browser_id: browserId };
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) console.log(await main());
