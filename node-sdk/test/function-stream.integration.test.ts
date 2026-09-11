import { createServer, type ServerResponse } from 'node:http';
import { once } from 'node:events';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';

// Real HTTP transport, generated client, redirects and SSE parsing; no credentials needed.
describe('Function streaming HTTP integration', () => {
	const finalResult = { function_id: 'fixture', function_run_id: 'run-1', status: 'closed', session_id: null, result: { text: 'café 🌍' } };
	let handle: (body: any, res: ServerResponse, path: string) => void;
	let baseUrl: string;
	let client: NotteClient;
	const server = createServer(async (req, res) => {
		const chunks = [];
		for await (const chunk of req) chunks.push(chunk);
		const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : undefined;
		if (req.url?.includes('/redirect/')) {
			res.writeHead(307, { location: `${baseUrl}/lambda` });
			res.end();
		} else handle(body, res, req.url!);
	});
	const event = (type: string, message: unknown) => `data: ${JSON.stringify({ type, message })}\r\n\r\n`;
	beforeAll(async () => {
		server.listen(0, '127.0.0.1');
		await once(server, 'listening');
		baseUrl = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
		client = new NotteClient({ baseUrl, apiKey: 'test-key' }); // pragma: allowlist secret
	});
	afterAll(async () => {
		server.closeAllConnections();
		await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
	});

	it.each([true, false])('creates a run, executes that ID and retrieves it (stream=%s)', async stream => {
		const paths: string[] = [];
		const metadata = { ...finalResult, created_at: '2026-09-11T00:00:00Z', updated_at: '2026-09-11T00:00:00Z', result: JSON.stringify(finalResult.result) };
		handle = (body, res, path) => {
			paths.push(path);
			if (path.endsWith('/create')) {
				expect(body).toEqual({ local: false });
				res.end(JSON.stringify({ function_id: 'fixture', function_run_id: 'run-1', created_at: metadata.created_at }));
			} else if (body) {
				expect(body).toMatchObject({ function_run_id: 'run-1', variables: { functionRunId: 'script-input' }, stream });
				res.end(stream ? event('result', JSON.stringify(finalResult)) : JSON.stringify(finalResult));
			} else {
				res.setHeader('content-type', 'application/json');
				res.end(JSON.stringify(metadata));
			}
		};
		const fn = client.NotteFunction({ function_id: 'fixture' });
		const created = await fn.createRun();
		expect(paths).toEqual(['/functions/fixture/runs/create']);
		expect(created.function_run_id).toBe('run-1');
		expect(await fn.run({ functionRunId: 'script-input' }, { functionRunId: created.function_run_id, stream })).toEqual(finalResult);
		expect(await fn.getRun(created.function_run_id)).toEqual(metadata);
		expect(await fn.retrieve(created.function_run_id)).toEqual(metadata);
		expect(paths).toEqual(['/functions/fixture/runs/create', '/functions/fixture/runs/run-1', '/functions/fixture/runs/run-1', '/functions/fixture/runs/run-1']);
	});

	it('does not implicitly reuse a pre-created run', async () => {
		const paths: string[] = [];
		handle = (_, res, path) => {
			paths.push(path);
			res.end(path.endsWith('/create') ? JSON.stringify({ function_run_id: 'unused' }) : event('result', JSON.stringify(finalResult)));
		};
		const fn = client.NotteFunction({ function_id: 'fixture' });
		await fn.createRun();
		await fn.run();
		expect(paths).toEqual(['/functions/fixture/runs/create', '/functions/fixture/runs/start']);
	});

	it('propagates createRun HTTP failures', async () => {
		handle = (_, res) => { res.writeHead(403); res.end(JSON.stringify({ message: 'Access denied' })); };
		await expect(client.NotteFunction({ function_id: 'fixture' }).createRun()).rejects.toThrow('Access denied');
	});

	it.each(['fixture', 'redirect'])('streams logs before resolving through %s transport', async functionId => {
		let finish!: () => void;
		let requestBody: any;
		handle = (body, res) => {
			requestBody = body;
			// Lambda can label its stream text/plain. It must not be buffered.
			res.writeHead(200, { 'content-type': 'text/plain' });
			res.write(': heartbeat\r\n\r\n' + event('session_start', 'session-1'));
			const bytes = Buffer.from(event('log', 'café 🌍'));
			const split = bytes.indexOf(Buffer.from('🌍')) + 1;
			res.write(bytes.subarray(0, split));
			setImmediate(() => res.write(bytes.subarray(split)));
			finish = () => res.end(event('result', JSON.stringify(finalResult)));
		};
		let logged!: () => void;
		const logReceived = new Promise<void>(resolve => { logged = resolve; });
		const onLog = vi.fn(() => logged());
		let settled = false;
		const pending = client.NotteFunction({ function_id: functionId }).run(
			{ stream: 'script-input', runtime: 'script-runtime' }, { runtime: 'extended', onLog },
		).finally(() => { settled = true; });
		try {
			await logReceived;
			expect(settled).toBe(false);
			expect(onLog).toHaveBeenCalledWith('café 🌍');
			expect(requestBody).toMatchObject({ stream: true, runtime: 'extended', variables: { stream: 'script-input', runtime: 'script-runtime' } });
		} finally { finish(); }
		expect(await pending).toEqual(finalResult);
	});

	it('returns the backend JSON result when streaming is disabled', async () => {
		let requestBody: any;
		handle = (body, res) => {
			requestBody = body;
			res.writeHead(200, { 'content-type': 'text/plain' });
			res.end(JSON.stringify(finalResult));
		};
		expect(await client.NotteFunction({ function_id: 'fixture' }).run({}, { stream: false })).toEqual(finalResult);
		expect(requestBody.stream).toBe(false);
	});

	it('prints logs by default and accepts a final frame without a trailing newline', async () => {
		handle = (_, res) => res.end(event('log', 'hello') + event('result', JSON.stringify(finalResult)).trimEnd());
		const log = vi.spyOn(console, 'log').mockImplementation(() => {});
		try {
			expect(await client.NotteFunction({ function_id: 'fixture' }).run()).toEqual(finalResult);
			expect(log).toHaveBeenCalledWith('hello');
		} finally { log.mockRestore(); }
	});

	it.each([
		['missing result', ': heartbeat\n\n', 'without a result'],
		['malformed event', 'data: {oops}\n\n', 'Failed to run function'],
		['invalid result', event('result', '{}'), 'Invalid function result'],
		['stream error', event('error', 'execution interrupted'), 'execution interrupted'],
		['failed execution', event('result', JSON.stringify({ ...finalResult, status: 'failed', result: 'boom' })), 'run-1 failed: boom'],
	])('rejects %s', async (_, payload, error) => {
		handle = (_, res) => res.end(payload);
		await expect(client.NotteFunction({ function_id: 'fixture' }).run()).rejects.toThrow(error);
	});

	it.each([true, false])('can return a failed result without throwing (stream=%s)', async stream => {
		const failure = { ...finalResult, status: 'failed', result: 'boom' };
		handle = (_, res) => res.end(stream ? event('result', JSON.stringify(failure)) : JSON.stringify(failure));
		expect(await client.NotteFunction({ function_id: 'fixture' }).run({}, { stream, raiseOnFailure: false })).toEqual(failure);
	});

	it('rejects failed non-streaming executions by default', async () => {
		handle = (_, res) => res.end(JSON.stringify({ ...finalResult, status: 'failed', result: 'boom' }));
		await expect(client.NotteFunction({ function_id: 'fixture' }).run({}, { stream: false })).rejects.toThrow('run-1 failed: boom');
	});

	it('rejects a disconnected stream', async () => {
		handle = (_, res) => {
			res.writeHead(200, { 'content-type': 'text/event-stream' });
			res.write(': heartbeat\n\n');
			setImmediate(() => res.destroy());
		};
		await expect(client.NotteFunction({ function_id: 'fixture' }).run()).rejects.toThrow('Failed to run function');
	});

	it('propagates HTTP errors', async () => {
		handle = (_, res) => { res.writeHead(403); res.end(JSON.stringify({ message: 'Access denied' })); };
		await expect(client.NotteFunction({ function_id: 'fixture' }).run()).rejects.toThrow('Access denied');
	});
});
