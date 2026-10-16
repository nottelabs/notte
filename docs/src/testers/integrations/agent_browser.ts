// @sniptest filename=notte_agent_browser.ts
// @sniptest typecheck_only=true
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { NotteClient } from 'notte-sdk';

const execute = promisify(execFile);

const client = new NotteClient();
export const result = await client.Session().use(async (session) => {
  const command = ['--session', `notte-${session.getId()!}`, '--json'];
  const env = { ...process.env, AGENT_BROWSER_CDP: await session.cdpUrl() };
  async function browser(...args: string[]): Promise<Record<string, unknown>> {
    try {
      const { stdout } = await execute('agent-browser', [...command, ...args], { env, timeout: 120_000 });
      const response = JSON.parse(stdout);
      if (!response?.success || typeof response.data !== 'object' || response.data === null) throw new Error('Unsuccessful CLI command');
      return response.data;
    } catch {
      // CLI errors can include the authenticated CDP URL.
      throw new Error('agent-browser command failed');
    }
  }
  let failed = false;
  try {
    await browser('open', 'https://example.com');
    const { title } = await browser('get', 'title');
    if (typeof title !== 'string') throw new Error('The title was not returned');
    console.log(title);
    return { title, session_id: session.getId()! };
  } catch (error) {
    failed = true;
    throw error;
  } finally {
    try { await browser('close'); }
    catch (error) { if (!failed) throw error; }
  }
});
