// @sniptest filename=manage_schedule.ts
// @sniptest show=3-21
const functionId = process.env.NOTTE_FUNCTION_ID!;

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({ function_id: functionId });
let schedule;
try {
  // Create or replace the schedule. Times are UTC.
  await fn.setSchedule({
    cron: '0 9 ? * * *',
    variables: { url: 'https://example.com' },
  });
  // Read the schedule from the function metadata.
  schedule = await fn.get();
  console.log(schedule.schedule_cron, schedule.schedule_state);
} finally {
  // Delete the schedule when it is no longer needed.
  await fn.deleteSchedule();
}

if (schedule.schedule_cron !== '0 9 ? * * *') throw new Error('Schedule was not saved');
const results = [schedule.schedule_cron === '0 9 ? * * *'];
export { results };
