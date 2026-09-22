// @sniptest filename=consume_stream.ts
// @sniptest show=1-48
const NOTTE_API_KEY = process.env.NOTTE_API_KEY as string;

const response = await fetch('https://anything.notte.cc/api/anything/start', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${NOTTE_API_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ query: 'fetch the top 3 hacker news posts' }),
});
if (!response.ok) {
  throw new Error(`HTTP ${response.status}`);
}
if (!response.body) {
  throw new Error('ReadableStream not available');
}

// The thread ID lets you send follow-up turns later
const threadId = response.headers.get('x-thread-id');
console.log('Thread ID:', threadId);

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
let finished = false;

while (!finished) {
  const result = await reader.read();
  if (result.done) break;

  buffer += decoder.decode(result.value, { stream: true });
  const lines = buffer.split('\n');
  // The last element is a partial line: keep it for the next chunk
  buffer = lines.pop() ?? '';

  for (const rawLine of lines) {
    // Lines may be terminated with CRLF, so drop any trailing carriage return
    const line = rawLine.replace(/\r$/, '');
    if (!line.startsWith('data: ')) continue;
    const payload = line.slice('data: '.length);
    if (payload === '[DONE]') {
      finished = true;
      break;
    }
    const chunk = JSON.parse(payload) as { type: string };
    console.log(chunk.type, chunk);
  }
}

export {};
