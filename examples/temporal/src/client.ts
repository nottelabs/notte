import { randomUUID } from 'node:crypto';
import { Client, Connection } from '@temporalio/client';
import { readNottePage } from './workflows';

async function main() {
  const connection = await Connection.connect({ address: process.env.TEMPORAL_ADDRESS ?? 'localhost:7233' });
  try {
    const client = new Client({ connection, namespace: process.env.TEMPORAL_NAMESPACE ?? 'default' });
    const result = await client.workflow.execute(readNottePage, {
      args: ['https://example.com'], taskQueue: 'notte-browser', workflowId: `notte-${randomUUID()}`,
      workflowExecutionTimeout: '15 minutes',
    });
    console.log(JSON.stringify(result));
  } finally {
    await connection.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
