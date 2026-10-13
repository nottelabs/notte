import { createServer } from 'node:http';
import { once } from 'node:events';
import { expect, it } from 'vitest';
import { NotteClient } from '@/index';
import { trackDeployments, cleanupDeployments, DEPLOYMENT_CHILD_TIMEOUT_MS, DEPLOYMENT_PAIR_TIMEOUT_MS, DEPLOYMENT_DRAIN_TIMEOUT_MS, DEPLOYMENT_CLEANUP_TIMEOUT_MS } from './helpers/deployment-tracker';

it('budgets both children plus bounded response draining and parent cleanup', () => {
  expect(DEPLOYMENT_PAIR_TIMEOUT_MS).toBeGreaterThan(2 * DEPLOYMENT_CHILD_TIMEOUT_MS + DEPLOYMENT_DRAIN_TIMEOUT_MS + DEPLOYMENT_CLEANUP_TIMEOUT_MS);
});

it('records a late creation reply even when the requesting child disconnects', async () => {
  const id = '00000000-0000-4000-8000-000000000001';
  const operations: string[] = [];
  let accept!: () => void;
  const accepted = new Promise<void>(resolve => { accept = resolve; });
  let reply!: () => void;
  const upstream = createServer((req, res) => {
    operations.push(`${req.method} ${req.url}`);
    res.setHeader('content-type', 'application/json');
    if (req.method === 'POST') {
      req.resume();
      reply = () => res.end(JSON.stringify({ function_id: id }));
      accept();
    } else if (req.method === 'GET') {
      res.end(JSON.stringify({ items: [], has_next: false }));
    } else res.end('{}');
  });
  upstream.listen(0, '127.0.0.1');
  await once(upstream, 'listening');
  const address = upstream.address();
  if (!address || typeof address === 'string') throw new Error('Missing address');
  const apiUrl = `http://127.0.0.1:${address.port}`;
  const tracker = await trackDeployments(apiUrl);
  const abort = new AbortController();
  try {
    const response = fetch(`${tracker.url}/functions`, { method: 'POST', body: 'fixture', signal: abort.signal }).catch(error => error);
    await accepted;
    abort.abort();
    await response;
    const closing = tracker.close();
    reply();
    await closing;
    expect([...tracker.ids]).toEqual([id]);
    await cleanupDeployments(new NotteClient({ baseUrl: apiUrl, apiKey: 'test' }), tracker.ids); // pragma: allowlist secret
    expect(operations).toContain(`DELETE /functions/${id}`);
  } finally {
    upstream.closeAllConnections();
    await new Promise<void>(resolve => upstream.close(() => resolve()));
  }
});

it('rejects paths outside the fixed function API without forwarding credentials', async () => {
  const tracker = await trackDeployments('https://example.com');
  try {
    const response = await fetch(`${tracker.url}/other`, { headers: { Authorization: 'test' } });
    expect(response.status).toBe(403);
    expect(tracker.ids.size).toBe(0);
  } finally { await tracker.close(); }
});

it('accepts an already soft-deleted function but still reports unrelated cleanup errors', async () => {
  const id = '00000000-0000-4000-8000-000000000002';
  let message = `The function '${id}' is not active. Please provide a different function_id`;
  let deletes = 0;
  const upstream = createServer((req, res) => {
    if (req.method === 'DELETE') deletes++;
    res.writeHead(400, { 'content-type': 'application/json' }).end(JSON.stringify({ message }));
  });
  upstream.listen(0, '127.0.0.1');
  await once(upstream, 'listening');
  const address = upstream.address();
  if (!address || typeof address === 'string') throw new Error('Missing address');
  const client = new NotteClient({ baseUrl: `http://127.0.0.1:${address.port}`, apiKey: 'test' }); // pragma: allowlist secret
  try {
    await cleanupDeployments(client, [id]);
    message = 'Unrelated bad request';
    await expect(cleanupDeployments(client, [id])).rejects.toThrow('Deployment cleanup failed');
    expect(deletes).toBe(2);
  } finally {
    upstream.closeAllConnections();
    await new Promise<void>(resolve => upstream.close(() => resolve()));
  }
});

it('preserves runtime redirects for the SDK instead of replaying the request body', async () => {
  const upstream = createServer((req, res) => {
    req.resume();
    res.writeHead(307, { location: 'https://runtime.example.invalid/invoke' }).end();
  });
  upstream.listen(0, '127.0.0.1');
  await once(upstream, 'listening');
  const address = upstream.address();
  if (!address || typeof address === 'string') throw new Error('Missing address');
  const tracker = await trackDeployments(`http://127.0.0.1:${address.port}`);
  try {
    const response = await fetch(`${tracker.url}/functions/id/runs/00000000-0000-4000-8000-000000000001`, {
      method: 'POST', body: '{"stream":false}', redirect: 'manual',
    });
    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe('https://runtime.example.invalid/invoke');
    await tracker.runStarted;
  } finally {
    await tracker.close();
    upstream.closeAllConnections();
    await new Promise<void>(resolve => upstream.close(() => resolve()));
  }
});
