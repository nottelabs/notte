// @sniptest filename=notte_openai_agents.ts
// @sniptest typecheck_only=true
import { Agent, MCPServerStreamableHttp, createMCPToolStaticFilter, Runner } from '@openai/agents';
import { NotteClient } from 'notte-sdk';
import { z } from 'zod';

export const result = await new NotteClient().Session().use(async (session) => {
  const server = new MCPServerStreamableHttp({
    name: 'Notte',
    url: new URL('/mcp', process.env.NOTTE_API_URL || 'https://api.notte.cc').href,
    requestInit: { headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY!}` } },
    clientSessionTimeoutSeconds: 120,
    toolFilter: createMCPToolStaticFilter({
      allowed: ['browser_action', 'browser_observe', 'browser_scrape'],
    }),
  });
  try {
    await server.connect();
    const agent = new Agent({
      name: 'Browser reader',
      model: 'gpt-4.1-mini',
      instructions: `Use only browser_id ${session.getId()!}. Read the page with Notte tools.`,
      mcpServers: [server],
      outputType: z.object({ title: z.string() }),
    });
    const answer = await new Runner({ tracingDisabled: true }).run(agent, 'Visit https://example.com and return its page title.', {
      maxTurns: 8,
    });
    if (!answer.finalOutput) throw new Error('The agent returned no title');
    console.log(answer.finalOutput.title);
    return { title: answer.finalOutput.title, session_id: session.getId()! };
  } finally {
    await server.close();
  }
});
