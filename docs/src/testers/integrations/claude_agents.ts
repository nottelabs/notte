// @sniptest filename=notte_claude_agent.ts
// @sniptest typecheck_only=true
import { query } from '@anthropic-ai/claude-agent-sdk';
import { NotteClient } from 'notte-sdk';

export const result = await new NotteClient().Session({ max_duration_minutes: 3 }).use(async (session) => {
  let title: unknown;
  try {
    for await (const message of query({
      prompt: `Use Notte tools with browser_id ${session.getId()!}. Visit https://example.com and read its page title.`,
      options: {
        model: process.env.ANTHROPIC_MODEL ?? 'claude-haiku-5-5',
        tools: [],
        settingSources: [],
        strictMcpConfig: true,
        permissionMode: 'dontAsk',
        allowedTools: ['browser_action', 'browser_observe', 'browser_scrape'].map(name => `mcp__notte__${name}`),
        mcpServers: {
          notte: {
            type: 'http',
            url: `${(process.env.NOTTE_API_URL || 'https://api.notte.cc').replace(/\/+$/, '')}/mcp`,
            headers: { Authorization: 'Bearer ${NOTTE_API_KEY}' },
          },
        },
        maxTurns: 8,
        outputFormat: {
          type: 'json_schema',
          schema: { type: 'object', properties: { title: { type: 'string' } }, required: ['title'] },
        },
      },
    })) {
      if (message.type === 'result' && message.subtype === 'success') {
        title = (message.structured_output as { title?: unknown } | undefined)?.title;
      }
    }
    if (typeof title !== 'string') throw new Error('The Claude agent returned no page title');
  } catch {
    throw new Error(`Claude agent failed (session ${session.getId()!})`);
  }
  console.log(title);
  return { title, session_id: session.getId()! };
});
