import { anthropic } from '@ai-sdk/anthropic';
import { createMCPClient } from '@ai-sdk/mcp';
import { OpenTelemetry } from '@ai-sdk/otel';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { getCurrentTraceId, observe, TraceRoot, updateCurrentTrace } from '@traceroot-ai/traceroot';
import { generateText, isStepCount, Output, registerTelemetry } from 'ai';
import { NotteClient } from 'notte-sdk';
import { z } from 'zod';

const TASK = 'Visit https://news.ycombinator.com and return the top 3 stories with their points.';
const TOOLS = ['browser_action', 'browser_observe', 'browser_scrape'];
const TopStories = z.object({ stories: z.array(z.object({ title: z.string(), points: z.number().int() })) });

const notteApiKey = process.env.NOTTE_API_KEY;
if (!notteApiKey) throw new Error('Set NOTTE_API_KEY');

// Records the agent run, each model call and each Notte tool call.
TraceRoot.initialize();
registerTelemetry(new OpenTelemetry({ usage: true }));

async function topStories(task: string) {
  return new NotteClient().Session({ max_duration_minutes: 5 }).use(async (session) => {
    const sessionId = session.getId();
    if (!sessionId) throw new Error('The Notte session has no ID');
    // Group every trace from this browser under its Notte session ID.
    updateCurrentTrace({ sessionId });
    const mcp = await createMCPClient({
      transport: new StreamableHTTPClientTransport(
        new URL(`${(process.env.NOTTE_API_URL || 'https://api.notte.cc').replace(/\/+$/, '')}/mcp`),
        { requestInit: { headers: { Authorization: `Bearer ${notteApiKey}` } } },
      ),
    });
    try {
      const tools = Object.fromEntries(Object.entries(await mcp.tools()).filter(([name]) => TOOLS.includes(name)));
      const { output } = await generateText({
        model: anthropic(process.env.ANTHROPIC_MODEL ?? 'claude-haiku-5-5'),
        instructions: `Use only browser_id ${sessionId}. Read pages with the Notte tools and report only what the page shows.`,
        prompt: task,
        tools,
        stopWhen: isStepCount(10),
        output: Output.object({ schema: TopStories }),
        telemetry: { functionId: 'hacker_news.top_stories' },
      });
      return { ...output, session_id: sessionId, trace_id: getCurrentTraceId() };
    } finally {
      await mcp.close();
    }
  });
}

try {
  const result = await observe({ name: 'hacker_news.top_stories', type: 'agent' }, topStories, TASK);
  console.log(JSON.stringify(result, null, 2));
} finally {
  await TraceRoot.shutdown();
}
