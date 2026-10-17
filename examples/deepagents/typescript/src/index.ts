import { ChatAnthropic } from '@langchain/anthropic';
import { MCPAdapter } from '@langchain/mcp-adapters';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { createDeepAgent, createFilesystemMiddleware } from 'deepagents';
import { NotteClient } from 'notte-sdk';
import { pathToFileURL } from 'node:url';

export function browserTools(tools: DynamicStructuredTool[], sessionId: string) {
  const names = ['notte_browser_action', 'notte_browser_observe', 'notte_browser_scrape'];
  const selected = tools.filter(tool => names.includes(tool.name));
  if (selected.length !== names.length) throw new Error('Required browser tools are unavailable');
  return selected.map(tool => new DynamicStructuredTool({
    name: tool.name, description: tool.description, schema: tool.schema,
    func: args => tool.invoke({ ...args, browser_id: sessionId }),
  }));
}

export async function run(task: string) {
  return new NotteClient().Session({ max_duration_minutes: 3 }).use(async session => {
    const adapter = new MCPAdapter({ servers: { notte: {
      url: `${(process.env.NOTTE_API_URL ?? 'https://api.notte.cc').replace(/\/+$/, '')}/mcp/`,
      headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` },
    } } });
    let stage = 'MCP connection and tool discovery';
    let failed = false;
    try {
      const tools = browserTools(await adapter.listTools(), session.getId()!);
      stage = 'agent initialization';
      const agent = createDeepAgent({
        model: new ChatAnthropic({
          model: process.env.DEEPAGENTS_MODEL ?? 'claude-haiku-5-5', maxTokens: 1024, maxRetries: 0,
          clientOptions: { timeout: 60_000, baseURL: process.env.ANTHROPIC_BASE_URL },
        }),
        tools,
        middleware: [createFilesystemMiddleware({ tools: ['read_file'] })],
        systemPrompt: `Use Notte browser tools with browser_id ${session.getId()} for every browser call. `
          + 'Navigate with notte_browser_action before reading. Report only what the browser shows.',
      });
      stage = 'agent execution';
      const result = await agent.invoke({ messages: [{ role: 'user', content: task }] }, { recursionLimit: 20 });
      return { answer: result.messages.at(-1)?.text ?? '', session_id: session.getId()! };
    } catch (error) {
      failed = true;
      for (let depth = 0; depth < 32 && error instanceof Error && error.cause instanceof Error; depth++) error = error.cause;
      const code = (error as { status?: unknown } | null)?.status;
      const status = typeof code === 'number' ? ` HTTP ${code}` : '';
      const category = error instanceof Error ? error.constructor.name : 'UnknownError';
      throw new Error(`Deep Agents failed during ${stage}: ${category}${status} (session ${session.getId()})`);
    } finally {
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        await Promise.race([
          adapter.close(),
          new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Close deadline exceeded')), 5000); }),
        ]);
      } catch {
        if (!failed) throw new Error('Deep Agents MCP cleanup failed');
      } finally { clearTimeout(timer); }
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  console.log(JSON.stringify(await run(process.argv.slice(2).join(' ') || 'Visit https://example.com and report its page title.')));
}
