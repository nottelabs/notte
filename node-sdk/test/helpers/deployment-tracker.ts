import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { once } from 'node:events';
import { NotteClient, NotteAPIError, functionDelete, functionRunStop, listFunctionRunsByFunctionId } from '@/index';

export const DEPLOYMENT_CHILD_TIMEOUT_MS = 120_000;
export const DEPLOYMENT_DRAIN_TIMEOUT_MS = 60_000;
export const DEPLOYMENT_CLEANUP_TIMEOUT_MS = 60_000;
export const DEPLOYMENT_PAIR_TIMEOUT_MS = 2 * DEPLOYMENT_CHILD_TIMEOUT_MS
  + DEPLOYMENT_DRAIN_TIMEOUT_MS + DEPLOYMENT_CLEANUP_TIMEOUT_MS + 30_000;
export const deploymentExamples = new Set([
  'functions/deploy_function.ts', 'functions/creating/deploy_sdk.ts',
  'functions/creating/deployment_options.ts', 'functions/management/private_function.ts',
]);

/** Parent-owned relay: record creation responses before the child receives them.
 * It forwards real SDK requests unchanged to one fixed API origin, never mocks them.
 */
export async function trackDeployments(apiUrl: string) {
  const origin = new URL(apiUrl);
  const ids = new Set<string>();
  let started!: () => void;
  const runStarted = new Promise<void>(resolve => { started = resolve; });
  const pending = new Set<Promise<void>>();
  const nonCreation = new Set<AbortController>();
  async function forward(req: IncomingMessage, res: ServerResponse) {
    const target = new URL(req.url ?? '/', origin);
    if (target.origin !== origin.origin || !/^\/functions(?:\/|$)/.test(target.pathname)) {
      res.writeHead(403).end();
      return;
    }
    const creating = req.method === 'POST' && target.pathname.replace(/\/$/, '') === '/functions';
    const running = req.method === 'POST' && /^\/functions\/[^/]+\/runs\/[0-9a-f-]{36}$/i.test(target.pathname);
    const abort = new AbortController();
    if (!creating) nonCreation.add(abort);
    try {
      const chunks: Buffer[] = [];
      for await (const chunk of req) chunks.push(Buffer.from(chunk));
      const headers = new Headers();
      for (const [key, value] of Object.entries(req.headers)) {
        if (value !== undefined && !['host', 'connection', 'content-length', 'transfer-encoding'].includes(key)) {
          headers.set(key, Array.isArray(value) ? value.join(',') : value);
        }
      }
      const request = fetch(target, {
        method: req.method, headers,
        body: chunks.length ? Buffer.concat(chunks) : undefined,
        // Let the SDK apply its normal runtime-redirect/authentication policy.
        redirect: 'manual',
        signal: AbortSignal.any([abort.signal, AbortSignal.timeout(DEPLOYMENT_DRAIN_TIMEOUT_MS)]),
      });
      if (running) started();
      const response = await request;
      if (creating && response.status >= 300 && response.status < 400) throw new Error('Unexpected creation redirect');
      const body = Buffer.from(await response.arrayBuffer());
      if (creating && response.ok) {
        const id: unknown = JSON.parse(body.toString()).function_id;
        if (typeof id !== 'string' || !/^[0-9a-f-]{36}$/i.test(id)) throw new Error('Invalid deployed function ID');
        ids.add(id);
      }
      if (!res.destroyed) {
        const type = response.headers.get('content-type');
        if (type) res.setHeader('content-type', type);
        const location = response.headers.get('location');
        if (location) res.setHeader('location', location);
        res.writeHead(response.status).end(body);
      }
    } catch (error) {
      if (!res.destroyed) res.writeHead(502).end('Deployment relay failed');
      // Expected when terminating an in-flight run after its child exits.
      if (!abort.signal.aborted) throw error;
    } finally {
      nonCreation.delete(abort);
    }
  }
  const errors: unknown[] = [];
  const server = createServer((req, res) => {
    const work = forward(req, res).catch(error => { errors.push(error); });
    pending.add(work);
    void work.finally(() => pending.delete(work));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Missing relay address');
  return {
    url: `http://127.0.0.1:${address.port}`, ids, runStarted,
    async close() {
      const closed = new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
      for (const request of nonCreation) request.abort();
      // An upload already accepted upstream must finish recording its ID even
      // if the child was killed before receiving the creation response.
      await Promise.all(pending);
      server.closeAllConnections();
      await closed;
      if (errors.length) throw new AggregateError(errors, 'Deployment relay failed');
    },
  };
}

/** Stop active runs and remove only IDs observed by this test's relay. */
export async function cleanupDeployments(client: NotteClient, ids: Iterable<string>) {
  const signal = AbortSignal.timeout(DEPLOYMENT_CLEANUP_TIMEOUT_MS);
  const errors: unknown[] = [];
  const missing = (error: unknown, id: string) => error instanceof NotteAPIError && (
    error.statusCode === 404 || (error.statusCode === 400
      && error.error?.message === `The function '${id}' is not active. Please provide a different function_id`)
  );
  for (const id of ids) {
    try {
      for (let page = 1; ; page++) {
        const runs = await listFunctionRunsByFunctionId({ client: client.getClient(), path: { function_id: id }, query: { page }, signal, throwOnError: true });
        for (const run of runs.data.items) {
          if (run.status === 'active') await functionRunStop({ client: client.getClient(), path: { function_id: id, run_id: run.function_run_id }, signal, throwOnError: true });
        }
        if (!runs.data.has_next) break;
      }
    } catch (error) { if (!missing(error, id)) errors.push(error); }
    try {
      await functionDelete({ client: client.getClient(), path: { function_id: id }, signal, throwOnError: true });
    } catch (error) { if (!missing(error, id)) errors.push(error); }
  }
  if (errors.length) throw new AggregateError(errors, 'Deployment cleanup failed');
}
