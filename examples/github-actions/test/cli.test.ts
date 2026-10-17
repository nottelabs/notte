import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

for (const language of ['python', 'typescript']) for (const interruption of ['SIGINT', 'SIGTERM'] as const) {
  test(`${language} CLI ${interruption} during a real claim reaps the browser`, { timeout: 95_000 }, async (t) => {
    const api = process.env.NOTTE_API_URL ?? 'https://api.notte.cc';
    let id = '';
    let interruptedAt = 0;
    let child: ReturnType<typeof spawn>;
    const server = createServer(async (req, res) => {
      let body = '';
      for await (const part of req) body += part.toString();
      try {
        const headers = new Headers();
        for (const [name, value] of Object.entries(req.headers)) if (value !== undefined && !['host', 'connection', 'content-length'].includes(name)) headers.set(name, String(value));
        const response = await fetch(`${api}${req.url}`, { method: req.method, headers, body: body || undefined, signal: AbortSignal.timeout(30_000), redirect: 'error' });
        const raw = await response.text();
        if (req.method === 'POST' && req.url?.startsWith('/sessions/start') && response.ok) {
          id = JSON.parse(raw).session_id;
          if (id) {
            interruptedAt = Date.now();
            child.kill(interruption);
            await sleep(150); // The remote claim exists while the caller still awaits its response.
          }
        }
        res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') ?? 'application/json' });
        res.end(raw);
      } catch { res.writeHead(502); res.end('{}'); }
    });
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    t.after(() => { server.closeAllConnections(); return new Promise<void>((resolve) => server.close(() => resolve())); });
    const command = language === 'python' ? process.env.NOTTE_EXAMPLE_PYTHON : process.execPath;
    assert.ok(command, 'Set NOTTE_EXAMPLE_PYTHON to the selected SDK interpreter');
    child = spawn(command, [fileURLToPath(new URL(language === 'python' ? '../repair.py' : '../repair.ts', import.meta.url))], {
      env: { ...process.env, NOTTE_API_URL: `http://127.0.0.1:${(server.address() as AddressInfo).port}` },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let output = '';
    child.stdout!.on('data', (part) => { output += part.toString(); });
    child.stderr!.on('data', (part) => { output += part.toString(); });
    const timer = setTimeout(() => child.kill('SIGKILL'), 80_000);
    t.after(() => { clearTimeout(timer); if (child.exitCode === null) child.kill('SIGKILL'); });
    const [code, signal] = await once(child, 'exit');
    assert.equal(code, interruption === 'SIGINT' ? 130 : 143);
    assert.equal(signal, null, 'The CLI must handle the signal and finish cleanup');
    assert.ok(id && interruptedAt, 'An actual remote claim must precede interruption');
    assert.ok(Date.now() - interruptedAt < 30_000, 'Claim cancellation must reap promptly');
    assert.ok(output.includes(id));
    assert.ok(!output.includes(process.env.NOTTE_API_KEY!));
    assert.ok(!output.includes('wss:'));
    const deadline = Date.now() + 15_000;
    while (true) {
      const response = await fetch(`${api}/sessions/${id}`, { headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY!}` }, signal: AbortSignal.timeout(20_000) });
      assert.equal(response.status, 200);
      const row = await response.json() as { status: string };
      if (row.status === 'closed') break;
      assert.ok(Date.now() < deadline, `Owned browser ${id} remains active`);
      await sleep(500);
    }
    console.log(`${language} CLI ${interruption}: owned browser ${id} independently closed`);
  });
}
