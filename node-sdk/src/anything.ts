import type { NotteClient } from '@/client';
import { NotteError } from '@/errors';
import type { AnythingStartErrors, AnythingStartRequest } from '@/lib/client/types.gen';

/** Body of `POST /anything/start`: the natural-language description of the task. */
export type AnythingStartOptions = AnythingStartRequest;

/**
 * One event of the AI SDK UI message stream. `type` names the event (for
 * example `text-delta`); the remaining keys depend on that type, so read them
 * at runtime rather than relying on a fixed shape.
 */
export type AnythingStreamChunk = { type: string } & Record<string, unknown>;

/**
 * Result of `POST /anything/start`. The endpoint answers with an
 * [AI SDK UI message stream](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol),
 * not a JSON document, so the run is exposed as chunks to iterate rather than
 * an object to read.
 */
export type AnythingStartResult = {
  /** Thread handling this run, from the `x-thread-id` response header. */
  threadId: string | null;
  /** Value of the `x-vercel-ai-ui-message-stream` header: the stream-format version. */
  uiMessageStreamVersion: string | null;
  /** Events of the stream, in order, until the terminating `[DONE]`. */
  chunks: AsyncGenerator<AnythingStreamChunk>;
};

/** Parse an AI SDK UI message stream into its events. */
async function* readAnythingStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<AnythingStreamChunk> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let end: number;
      while ((end = buffer.indexOf('\n')) !== -1) {
        // Frames may be terminated with CRLF; drop the carriage return.
        const line = buffer.slice(0, end).replace(/\r$/, '');
        buffer = buffer.slice(end + 1);
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).replace(/^ /, '');
        if (payload === '[DONE]') return;
        try {
          yield JSON.parse(payload) as AnythingStreamChunk;
        } catch (error) {
          throw new NotteError(`Malformed Anything stream event: ${payload}`, { cause: error });
        }
      }
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

/**
 * Anything API, the counterpart of `POST /anything/start`: turn a plain-English
 * description of a web task into a running automation.
 *
 * ```ts
 * const { threadId, chunks } = await client.anything.start({ task: 'fetch the top 3 hacker news posts' });
 * console.log('Thread ID:', threadId);
 * for await (const chunk of chunks) {
 *   console.log(chunk.type, chunk);
 * }
 * ```
 */
export class NotteAnything {
  private readonly client: NotteClient;

  constructor(client: NotteClient) {
    this.client = client;
  }

  /**
   * Start a run for `task` and stream the agent's progress back.
   *
   * Running is slow (minutes) and billable; prefer the marketplace
   * (`client.functions.list()`) when a ready-made function already fits.
   *
   * The returned `chunks` generator holds the connection open — iterate it to
   * completion, or `return`/`break` out of the loop to cancel and release the
   * stream.
   *
   * ```ts
   * const run = await client.anything.start({ task: 'get the weather in Paris' });
   * for await (const chunk of run.chunks) {
   *   if (chunk.type === 'text-delta') process.stdout.write(String(chunk.delta ?? ''));
   * }
   * ```
   *
   * Rejects with a `NotteAPIError` when the API answers with a non-2xx status.
   */
  async start(body: AnythingStartOptions): Promise<AnythingStartResult> {
    // Not the generated `anythingStart`: it reads the stream with the SSE client, which hides the
    // response headers, turns a non-2xx answer into a plain `Error` and retries a failed stream by
    // sending the POST again, which would start a second run.
    const { data, response } = await this.client
      .getClient()
      .post<{ 200: ReadableStream<Uint8Array> }, AnythingStartErrors, true>({
        security: [{ scheme: 'bearer', type: 'http' }],
        url: '/anything/start',
        body,
        headers: { 'Content-Type': 'application/json' },
        parseAs: 'stream',
        throwOnError: true,
      });
    const stream = data as ReadableStream<Uint8Array> | null | undefined;
    if (!stream) {
      throw new NotteError('Anything start returned no response stream');
    }
    return {
      threadId: response.headers.get('x-thread-id'),
      uiMessageStreamVersion: response.headers.get('x-vercel-ai-ui-message-stream'),
      chunks: readAnythingStream(stream),
    };
  }
}
