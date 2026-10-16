import { browserAgent } from './agent.ts';

const result = await browserAgent.run('Read the title of https://example.com');
console.log(JSON.stringify(result.toolCalls, null, 2));
