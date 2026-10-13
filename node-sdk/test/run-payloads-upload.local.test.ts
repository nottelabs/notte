import { createServer } from 'node:http';
import { once } from 'node:events';
import { createHash } from 'node:crypto';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';

// Exercise the public helper and real API transport; replace only private storage.
describe('run payload upload HTTP integration', () => {
	const requests: { method: string; path: string; body: any }[] = [];
	const nativeFetch = globalThis.fetch;
	let client: NotteClient;
	let referenceMismatch = false;
	const server = createServer(async (req, res) => {
		const chunks = [];
		for await (const chunk of req) chunks.push(chunk);
		const body = JSON.parse(Buffer.concat(chunks).toString());
		requests.push({ method: req.method!, path: req.url!, body });
		res.setHeader('Content-Type', 'application/json');
		if (req.method === 'POST') {
			res.end(JSON.stringify({
				reference: { ...body, size_bytes: body.size_bytes + (referenceMismatch ? 1 : 0), upload_id: 'upload-1' },
				url: 'https://storage.example/object',
				headers: { 'Content-Type': 'application/json', 'Content-Length': String(body.size_bytes), 'x-amz-checksum-sha256': body.sha256, 'If-None-Match': '*' },
			}));
		} else res.end(JSON.stringify({ success: true }));
	});
	beforeAll(async () => {
		server.listen(0, '127.0.0.1');
		await once(server, 'listening');
		client = new NotteClient({ baseUrl: `http://127.0.0.1:${(server.address() as { port: number }).port}`, apiKey: 'test-key' }); // pragma: allowlist secret
	});
	beforeEach(() => { requests.length = 0; referenceMismatch = false; });
	afterEach(() => vi.unstubAllGlobals());
	afterAll(async () => {
		server.closeAllConnections();
		await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
	});
	function mockStorage(status = 200) {
		const storage = vi.fn().mockResolvedValue(new Response('', { status }));
		vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) =>
			String(input) === 'https://storage.example/object' ? storage(input, init) : nativeFetch(input, init));
		return storage;
	}
	it('preserves omitted fields and normalizes small structured results', async () => {
		const storage = mockStorage();
		await client.NotteFunction({ function_id: 'fn' }).updateRun('run', { status: 'closed', result: { count: 2 } });
		expect(requests).toEqual([{ method: 'PATCH', path: '/functions/fn/runs/run', body: { status: 'closed', result: '{"count":2}' } }]);
		expect(storage).not.toHaveBeenCalled();
	});
	it('uploads UTF-8 bytes without API credentials before finalizing references', async () => {
		const storage = mockStorage();
		const logs = ['é'.repeat(600_000)];
		await client.NotteFunction({ function_id: 'fn' }).updateRun('run', { status: 'closed', logs });
		expect(requests.map(r => r.method)).toEqual(['POST', 'PATCH']);
		const upload = storage.mock.calls[0][1];
		expect(JSON.parse(upload.body.toString())).toEqual(logs);
		expect(upload.headers).not.toHaveProperty('Authorization');
		expect(upload.headers).not.toHaveProperty('x-notte-api-key');
		expect(upload.redirect).toBe('error');
		expect(requests[0].body).toEqual({ size_bytes: upload.body.length, sha256: createHash('sha256').update(upload.body).digest('base64') });
		expect(requests[1].body).toEqual({ status: 'closed', payloads: { logs: { ...requests[0].body, upload_id: 'upload-1' } } });
	});
	it('keeps a bounded result preview', async () => {
		mockStorage();
		await client.NotteFunction({ function_id: 'fn' }).updateRun('run', { status: 'closed', result: 'a'.repeat(1_100_000) });
		expect(requests[1].body.result_preview).toHaveLength(16000);
		expect(requests[1].body).not.toHaveProperty('result');
	});
	it('does not finalize a failed upload', async () => {
		mockStorage(503);
		await expect(client.NotteFunction({ function_id: 'fn' }).updateRun('run', { status: 'closed', logs: ['a'.repeat(1_100_000)] })).rejects.toThrow('upload failed');
		expect(requests.map(r => r.method)).toEqual(['POST']);
	});
	it('rejects mismatched upload references before transferring bytes', async () => {
		const storage = mockStorage();
		referenceMismatch = true;
		await expect(client.NotteFunction({ function_id: 'fn' }).updateRun('run', { status: 'closed', logs: ['a'.repeat(1_100_000)] })).rejects.toThrow('reference does not match');
		expect(storage).not.toHaveBeenCalled();
		expect(requests.map(r => r.method)).toEqual(['POST']);
	});
});
