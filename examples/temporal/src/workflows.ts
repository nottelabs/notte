import { proxyActivities } from '@temporalio/workflow';
import type * as activities from './activities';

const { readPage } = proxyActivities<typeof activities>({
  startToCloseTimeout: '4 minutes',
  retry: { maximumAttempts: 3 },
});

export async function readNottePage(url: string) {
  return readPage({ url });
}
