import type { NotteClient } from '@/client';
import type { AnythingStartRequest } from '@/lib/client/types.gen';
import { anythingStart } from '@/lib/client/sdk.gen';

/** Body of `POST /anything/start`: the natural-language description of the task. */
export type AnythingStartOptions = AnythingStartRequest;

/**
 * Response of `POST /anything/start`. The OpenAPI spec declares the 200
 * response as an untyped JSON object (`{}`), so the SDK exposes it as an
 * opaque record. In practice the Anything API answers with a reference to the
 * function it built for the task (for example a `function_id`), which can then
 * be run through `client.NotteFunction({ function_id })`. Check the keys at
 * runtime rather than relying on a fixed shape.
 */
export type AnythingStartResponse = Record<string, unknown>;

/**
 * Anything API, the counterpart of `POST /anything/start`: turn a plain-English
 * description of a web task into a deployed, reusable function.
 *
 * ```ts
 * const started = await client.anything.start({ task: 'fetch the top 3 hacker news posts' });
 * console.log(started);
 * ```
 */
export class NotteAnything {
  private readonly client: NotteClient;

  constructor(client: NotteClient) {
    this.client = client;
  }

  /**
   * Start building a function for `task`. Building is slow (minutes) and
   * billable; prefer the marketplace (`client.functions.list()`) when a
   * ready-made function already fits.
   *
   * ```ts
   * const result = await client.anything.start({ task: 'get the weather in Paris' });
   * if (typeof result.function_id === 'string') {
   *   const fn = client.NotteFunction({ function_id: result.function_id });
   * }
   * ```
   *
   * Rejects with a `NotteAPIError` when the API answers with a non-2xx status.
   */
  async start(body: AnythingStartOptions): Promise<AnythingStartResponse> {
    const response = await anythingStart({
      client: this.client.getClient(),
      body,
      throwOnError: true,
    });
    return (response.data ?? {}) as AnythingStartResponse;
  }
}
