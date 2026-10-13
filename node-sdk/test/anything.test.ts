import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NotteClient } from '@/client';

const mocks = vi.hoisted(() => ({
  anythingStart: vi.fn(),
}));

vi.mock('@/lib/client/sdk.gen', () => mocks);

import { NotteAnything } from '@/anything';

/** A `text/event-stream` body, as the `/anything/start` proxy pipes it back. */
function streamOf(...frames: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
}

function responseWith(headers: Record<string, string>): Response {
  return new Response(null, { headers });
}

async function collect<T>(chunks: AsyncGenerator<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const chunk of chunks) out.push(chunk);
  return out;
}

describe('NotteAnything', () => {
  const generated = { id: 'test-client' };
  const client = { getClient: () => generated } as unknown as NotteClient;
  let anything: NotteAnything;

  beforeEach(() => {
    mocks.anythingStart.mockReset();
    anything = new NotteAnything(client);
  });

  it('posts the task body and requests the raw stream', async () => {
    mocks.anythingStart.mockResolvedValue({
      data: streamOf('data: [DONE]\n\n'),
      response: responseWith({}),
    });

    await anything.start({ task: 'fetch the top 3 hacker news posts' });

    expect(mocks.anythingStart).toHaveBeenCalledTimes(1);
    expect(mocks.anythingStart).toHaveBeenCalledWith({
      client: generated,
      body: { task: 'fetch the top 3 hacker news posts' },
      parseAs: 'stream',
      throwOnError: true,
    });
  });

  it('exposes the thread and stream-format headers', async () => {
    mocks.anythingStart.mockResolvedValue({
      data: streamOf('data: [DONE]\n\n'),
      response: responseWith({
        'x-thread-id': '820a7cff-613b-4529-9ba4-52c7a6777713',
        'x-vercel-ai-ui-message-stream': 'v1',
      }),
    });

    const run = await anything.start({ task: 'x' });

    expect(run.threadId).toBe('820a7cff-613b-4529-9ba4-52c7a6777713');
    expect(run.uiMessageStreamVersion).toBe('v1');
  });

  it('reports absent headers as null rather than inventing them', async () => {
    mocks.anythingStart.mockResolvedValue({
      data: streamOf('data: [DONE]\n\n'),
      response: responseWith({}),
    });

    const run = await anything.start({ task: 'x' });

    expect(run.threadId).toBeNull();
    expect(run.uiMessageStreamVersion).toBeNull();
  });

  it('yields the parsed events of the stream in order', async () => {
    mocks.anythingStart.mockResolvedValue({
      data: streamOf(
        'data: {"type":"start"}\n\n',
        'data: {"type":"text-delta","delta":"hi"}\n\n',
        'data: [DONE]\n\n',
      ),
      response: responseWith({}),
    });

    const run = await anything.start({ task: 'x' });

    expect(await collect(run.chunks)).toEqual([
      { type: 'start' },
      { type: 'text-delta', delta: 'hi' },
    ]);
  });

  it('parses frames split across chunk boundaries', async () => {
    mocks.anythingStart.mockResolvedValue({
      data: streamOf('data: {"type":"st', 'art"}\n\ndata: [DO', 'NE]\n\n'),
      response: responseWith({}),
    });

    const run = await anything.start({ task: 'x' });

    expect(await collect(run.chunks)).toEqual([{ type: 'start' }]);
  });

  it('parses CRLF-terminated frames', async () => {
    mocks.anythingStart.mockResolvedValue({
      data: streamOf('data: {"type":"start"}\r\n\r\ndata: [DONE]\r\n\r\n'),
      response: responseWith({}),
    });

    const run = await anything.start({ task: 'x' });

    expect(await collect(run.chunks)).toEqual([{ type: 'start' }]);
  });

  it('stops at [DONE] without yielding it', async () => {
    mocks.anythingStart.mockResolvedValue({
      data: streamOf('data: [DONE]\n\ndata: {"type":"ignored"}\n\n'),
      response: responseWith({}),
    });

    const run = await anything.start({ task: 'x' });

    expect(await collect(run.chunks)).toEqual([]);
  });

  it('throws on a malformed event instead of yielding it', async () => {
    mocks.anythingStart.mockResolvedValue({
      data: streamOf('data: {not json}\n\n'),
      response: responseWith({}),
    });

    const run = await anything.start({ task: 'x' });

    await expect(collect(run.chunks)).rejects.toThrow('Malformed Anything stream event');
  });

  it('throws when the API sends no stream', async () => {
    mocks.anythingStart.mockResolvedValue({ data: undefined, response: responseWith({}) });

    await expect(anything.start({ task: 'noop' })).rejects.toThrow('no response stream');
  });

  it('propagates rejections from the generated operation', async () => {
    const failure = new Error('boom');
    mocks.anythingStart.mockRejectedValue(failure);

    await expect(anything.start({ task: 'x' })).rejects.toBe(failure);
  });
});
