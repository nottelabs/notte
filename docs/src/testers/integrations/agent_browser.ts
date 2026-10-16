// @sniptest filename=notte_agent_browser.ts
// @sniptest typecheck_only=true
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { NotteClient } from 'notte-sdk';

const execute = promisify(execFile);

export const result = await new NotteClient().Session().use(async (session) => {
  const command = ['--session', `notte-${session.getId()!}`, '--json'];
  async function browser(...args: string[]): Promise<Record<string, unknown>> {
    let stdout: string;
    try {
      ({ stdout } = await execute('agent-browser', [...command, ...args], { timeout: 120_000 }));
    } catch {
      // CLI errors can include the authenticated CDP URL.
      throw new Error('agent-browser command failed');
    }
    const response = JSON.parse(stdout);
    if (!response.success) throw new Error('agent-browser reported an unsuccessful command');
    return response.data;
  }
  try {
    await browser('connect', await session.cdpUrl());
    await browser('open', 'https://example.com');
    const { title } = await browser('get', 'title');
    if (typeof title !== 'string') throw new Error('The title was not returned');
    console.log(title);
    return { title, session_id: session.getId()! };
  } finally {
    await browser('close');
  }
});
