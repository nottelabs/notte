import { randomBytes } from 'node:crypto';
import { createServer } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';
import WebSocket, { WebSocketServer } from 'ws';

export async function cdpBridge(cdpUrl: string, signal?: AbortSignal) {
  signal?.throwIfAborted();
  const upstream = new WebSocket(cdpUrl, { handshakeTimeout: 30_000 });
  upstream.on('error', () => {}); // Never log authenticated CDP URLs.
  const abortMetadata = () => upstream.terminate();
  signal?.addEventListener('abort', abortMetadata, { once: true });
  let closeBridge: (() => Promise<void>) | undefined;
  try {
    await once(upstream, 'open');
    async function command(id: number, method: string) {
      let listener: (data: WebSocket.RawData) => void;
      let onClose: () => void;
      let timer: ReturnType<typeof setTimeout>;
      const result = new Promise<any>((resolve, reject) => {
        listener = (data: WebSocket.RawData) => {
          try {
            const message = JSON.parse(data.toString());
            if (message.id === id) message.error ? reject(new Error('CDP discovery failed')) : resolve(message.result);
          } catch { reject(new Error('Invalid CDP discovery response')); }
        };
        onClose = () => reject(new Error('Hosted browser connection closed'));
        timer = setTimeout(onClose, 30_000).unref();
        upstream.on('message', listener);
        upstream.once('close', onClose);
      });
      upstream.send(JSON.stringify({ id, method }));
      try { return await result; }
      finally { clearTimeout(timer!); upstream.off('message', listener!); upstream.off('close', onClose!); }
    }
    const version = await command(1, 'Browser.getVersion');
    const { targetInfos } = await command(2, 'Target.getTargets');
    upstream.terminate();
    const nonce = `/devtools/browser/${randomBytes(24).toString('hex')}`;
    const sockets = new Set<WebSocket>();
    let address = '';
    let endpoint = '';
    const server = createServer((req, res) => {
      if (req.headers.origin || ![address, '127.0.0.1'].includes(req.headers.host ?? '')) { res.writeHead(403).end(); return; }
      let payload;
      if (req.url?.replace(/\/$/, '') === '/json/version') {
        payload = { Browser: version.product, 'Protocol-Version': version.protocolVersion,
          'User-Agent': version.userAgent, 'V8-Version': version.jsVersion,
          'WebKit-Version': `537.36 (${version.revision})`, webSocketDebuggerUrl: endpoint };
      } else if (['/json', '/json/list'].includes(req.url?.replace(/\/$/, '') ?? '')) {
        payload = targetInfos.filter((x: any) => x.type === 'page').map((x: any) => ({
          id: x.targetId, type: x.type, title: x.title, url: x.url, webSocketDebuggerUrl: endpoint,
        }));
      } else { res.writeHead(404).end(); return; }
      res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify(payload));
    });
    const websocket = new WebSocketServer({ noServer: true });
    server.on('upgrade', (req, socket, head) => {
      // ChromeDriver's WebSocket handshake omits the port from Host.
      if (req.headers.origin || ![address, '127.0.0.1'].includes(req.headers.host ?? '') || req.url !== nonce) {
        socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');
        return;
      }
      websocket.handleUpgrade(req, socket, head, client => {
        const remote = new WebSocket(cdpUrl, { handshakeTimeout: 30_000 });
        const pending: { data: WebSocket.RawData; binary: boolean }[] = [];
        let pendingBytes = 0;
        sockets.add(client); sockets.add(remote);
        client.on('error', () => remote.terminate());
        remote.on('error', () => client.close(1011, 'Hosted browser connection closed'));
        client.on('message', (data, binary) => {
          if (remote.readyState === WebSocket.OPEN) remote.send(data, { binary });
          else if (remote.readyState === WebSocket.CONNECTING) {
            pendingBytes += Buffer.byteLength(data as Buffer);
            if (pendingBytes > 1_048_576) { client.close(1009, 'Connection buffer exceeded'); remote.terminate(); }
            else pending.push({ data, binary });
          }
        });
        remote.on('open', () => {
          for (const { data, binary } of pending) remote.send(data, { binary });
          pending.length = 0;
          pendingBytes = 0;
          remote.on('message', (data, binary) => client.readyState === WebSocket.OPEN && client.send(data, { binary }));
        });
        client.on('close', () => { sockets.delete(client); remote.close(); });
        remote.on('close', code => {
          sockets.delete(remote);
          client.close(code === 1000 || code === 1001 ? 1000 : 1011, 'Hosted browser connection closed');
        });
      });
    });
    server.listen(0, '127.0.0.1');
    let closing: Promise<void> | undefined;
    const abort = () => { void closeBridge?.().catch(() => {}); };
    closeBridge = () => closing ??= (async () => {
      signal?.removeEventListener('abort', abort);
      for (const socket of sockets) socket.terminate();
      websocket.close();
      server.closeAllConnections();
      await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    })();
    await once(server, 'listening');
    address = `127.0.0.1:${(server.address() as AddressInfo).port}`;
    endpoint = `ws://${address}${nonce}`;
    signal?.throwIfAborted();
    signal?.addEventListener('abort', abort, { once: true });
    return { address, close: closeBridge };
  } catch {
    upstream.terminate();
    await closeBridge?.().catch(() => {});
    throw new Error('Could not open the hosted browser bridge');
  } finally {
    signal?.removeEventListener('abort', abortMetadata);
  }
}
