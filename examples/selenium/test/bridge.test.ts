import assert from 'node:assert/strict';
import { once } from 'node:events';
import { request } from 'node:http';
import { test } from 'node:test';
import WebSocket, { WebSocketServer } from 'ws';
import { cdpBridge } from '../src/bridge.ts';

const version = { product: 'Chrome/150.0.0.0', protocolVersion: '1.3', userAgent: 'test', jsVersion: '1', revision: '@test' };

test('loopback discovery, forwarding, rejection and cleanup without credentials', { timeout: 15_000 }, async () => {
  const upstream = new WebSocketServer({ host: '127.0.0.1', port: 0 });
  await once(upstream, 'listening');
  const port = (upstream.address() as { port: number }).port;
  upstream.on('connection', socket => socket.on('message', data => {
    const message = JSON.parse(data.toString());
    if (message.method === 'Test.disconnect') { socket.close(1011, 'test failure'); return; }
    const result = message.method === 'Browser.getVersion' ? version : { targetInfos: [{ targetId: 'page1', type: 'page', url: 'about:blank', title: '' }] };
    socket.send(JSON.stringify({ id: message.id, result }));
  }));
  const cdpUrl = `ws://127.0.0.1:${port}/?token=test-only`;
  const bridge = await cdpBridge(cdpUrl);
  let bridgeClosed = false;
  try {
    const response = await fetch(`http://${bridge.address}/json/version`);
    const metadata = await response.json();
    assert.equal(metadata.Browser, version.product);
    assert.ok(!JSON.stringify(metadata).includes(cdpUrl), 'Discovery must hide the authenticated endpoint');
    assert.equal(new URL(metadata.webSocketDebuggerUrl).hostname, '127.0.0.1');
    assert.equal((await (await fetch(`http://${bridge.address}/json/list`)).json())[0].id, 'page1');
    assert.equal((await fetch(`http://${bridge.address}/json/version`, { headers: { Origin: 'https://untrusted.example' } })).status, 403);
    const untrustedHost = await new Promise<number>((resolve, reject) => {
      const req = request(`http://${bridge.address}/json/version`, { headers: { Host: 'untrusted.example' } }, res => {
        res.resume(); resolve(res.statusCode!);
      });
      req.on('error', reject); req.end();
    });
    assert.equal(untrustedHost, 403);
    for (const [url, options] of [[`ws://${bridge.address}/wrong`, {}], [metadata.webSocketDebuggerUrl, { origin: 'https://untrusted.example' }]] as const) {
      const rejected = new WebSocket(url, { ...options, handshakeTimeout: 1000 });
      await assert.rejects(once(rejected, 'open'), /403|404/);
    }
    const client = new WebSocket(metadata.webSocketDebuggerUrl);
    await once(client, 'open');
    const reply = once(client, 'message');
    client.send(JSON.stringify({ id: 3, method: 'Browser.getVersion' }));
    assert.deepEqual(JSON.parse((await reply)[0].toString()).result, version);
    const closed = once(client, 'close');
    client.send(JSON.stringify({ id: 4, method: 'Test.disconnect' }));
    const [code, reason] = await closed;
    assert.equal(code, 1011);
    assert.equal(reason.toString(), 'Hosted browser connection closed');
    const active = new WebSocket(metadata.webSocketDebuggerUrl);
    await once(active, 'open');
    const shutdown = once(active, 'close');
    await bridge.close();
    bridgeClosed = true;
    await shutdown;
    await assert.rejects(fetch(`http://${bridge.address}/json/version`));
    for (let attempt = 0; attempt < 100 && upstream.clients.size; attempt++) await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(upstream.clients.size, 0);
  } finally {
    if (!bridgeClosed) await bridge.close();
    for (const socket of upstream.clients) socket.terminate();
    await new Promise<void>(resolve => upstream.close(() => resolve()));
  }
});
