// @sniptest filename=start_detached.ts
// @sniptest show=1-19
const NOTTE_API_KEY = process.env.NOTTE_API_KEY as string;

const response = await fetch('https://anything.notte.cc/api/anything/start', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${NOTTE_API_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ query: 'fetch the top 3 hacker news posts', detach: true }),
});
if (!response.ok) {
  throw new Error(`HTTP ${response.status}`);
}

// 202 Accepted
const run = (await response.json()) as { thread_id: string; status: string; url: string };
console.log('Thread ID:', run.thread_id);
console.log('Status:', run.status); // "started"
console.log('Follow along at:', run.url);

export {};
