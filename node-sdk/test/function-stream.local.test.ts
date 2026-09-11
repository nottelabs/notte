import { createServer, type ServerResponse } from 'node:http';
import { once } from 'node:events';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';
import { FailedToRunCloudFunctionError, NotteAPIError, NotteError, NotteTimeoutError } from '@/errors';

type Headers = Record<string, string | string[] | undefined>;

// Real HTTP transport, generated client, redirects and SSE parsing; no credentials needed.
describe('Function streaming HTTP integration', () => {
	const finalResult = { function_id: 'fixture', function_run_id: 'run-1', status: 'closed', session_id: null, result: { text: 'café 🌍' } };
	const createdRecord = { function_id: 'fixture', function_run_id: 'run-1', created_at: '2026-09-11T00:00:00Z', status: 'created' };
	// `run()` creates a record before executing it (like Python). `handle` sees
	// only the execution request; override `handleCreate` to inspect the creation.
	let handle: (body: any, res: ServerResponse, path: string, headers: Headers) => void;
	let handleCreate: (body: any, res: ServerResponse, path: string, headers: Headers) => void;
	const defaultCreate: typeof handleCreate = (_, res) => res.end(JSON.stringify(createdRecord));
	const isCreate = (body: any) => body !== undefined && 'local' in body && !('variables' in body);
	let baseUrl: string;
	let client: NotteClient;
	const server = createServer(async (req, res) => {
		const chunks = [];
		for await (const chunk of req) chunks.push(chunk);
		const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : undefined;
		if (req.url?.includes('/redirect/')) {
			res.writeHead(307, { location: `${baseUrl}/lambda` });
			res.end();
		} else if (isCreate(body)) handleCreate(body, res, req.url!, req.headers);
		else handle(body, res, req.url!, req.headers);
	});
	const event = (type: string, message: unknown) => `data: ${JSON.stringify({ type, message })}\r\n\r\n`;
	beforeAll(async () => {
		server.listen(0, '127.0.0.1');
		await once(server, 'listening');
		baseUrl = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
		client = new NotteClient({ baseUrl, apiKey: 'test-key' }); // pragma: allowlist secret
	});
	beforeEach(() => {
		handleCreate = defaultCreate;
	});
	afterAll(async () => {
		server.closeAllConnections();
		await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
	});

	it.each([true, false])('creates a run, executes that ID and retrieves it (stream=%s)', async stream => {
		const paths: string[] = [];
		const metadata = { ...finalResult, created_at: '2026-09-11T00:00:00Z', updated_at: '2026-09-11T00:00:00Z', result: JSON.stringify(finalResult.result) };
		handleCreate = (body, res, path) => {
			paths.push(path);
			expect(body).toEqual({ local: false });
			res.end(JSON.stringify(createdRecord));
		};
		handle = (body, res, path) => {
			paths.push(path);
			if (body) {
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
		expect(created).toEqual(createdRecord);
		expect(await fn.run({ functionRunId: 'script-input' }, { functionRunId: created.function_run_id, stream })).toEqual(finalResult);
		expect(await fn.getRun(created.function_run_id)).toEqual(metadata);
		expect(await fn.retrieve(created.function_run_id)).toEqual(metadata);
		expect(paths).toEqual(['/functions/fixture/runs/create', '/functions/fixture/runs/run-1', '/functions/fixture/runs/run-1', '/functions/fixture/runs/run-1']);
	});

	it('creates its own record instead of reusing a pre-created run', async () => {
		const paths: string[] = [];
		let creations = 0;
		handleCreate = (_, res, path) => {
			paths.push(path);
			creations += 1;
			res.end(JSON.stringify({ ...createdRecord, function_run_id: `run-${creations}` }));
		};
		handle = (body, res, path) => {
			paths.push(path);
			expect(body.function_run_id).toBe('run-2');
			res.end(event('result', JSON.stringify({ ...finalResult, function_run_id: 'run-2' })));
		};
		const fn = client.NotteFunction({ function_id: 'fixture' });
		await fn.createRun();
		expect((await fn.run()).function_run_id).toBe('run-2');
		expect(paths).toEqual(['/functions/fixture/runs/create', '/functions/fixture/runs/create', '/functions/fixture/runs/run-2']);
	});

	it('sends the bearer token everywhere and the api key only to the execution endpoint', async () => {
		const seen: { path: string; headers: Headers }[] = [];
		handleCreate = (_, res, path, headers) => {
			seen.push({ path, headers });
			res.end(JSON.stringify(createdRecord));
		};
		handle = (_, res, path, headers) => {
			seen.push({ path, headers });
			res.end(event('result', JSON.stringify(finalResult)));
		};
		const fn = client.NotteFunction({ function_id: 'fixture' });
		await fn.run();
		const created = await fn.createRun();
		await fn.run({}, { functionRunId: created.function_run_id });
		expect(seen.map(({ path }) => path)).toEqual([
			'/functions/fixture/runs/create', '/functions/fixture/runs/run-1', '/functions/fixture/runs/create', '/functions/fixture/runs/run-1',
		]);
		for (const { path, headers } of seen) {
			expect(headers.authorization).toBe('Bearer test-key');
			expect(headers['x-notte-timeout-ms']).toBeUndefined();
			expect(headers['x-notte-request-origin']).toBe('sdk-node');
			expect(headers['x-notte-api-key']).toBe(path.endsWith('/create') ? undefined : 'test-key');
		}
	});

	it('propagates createRun HTTP failures as NotteAPIError', async () => {
		handleCreate = (_, res) => { res.writeHead(403); res.end(JSON.stringify({ message: 'Access denied' })); };
		const rejection = client.NotteFunction({ function_id: 'fixture' }).createRun();
		await expect(rejection).rejects.toBeInstanceOf(NotteAPIError);
		await expect(rejection).rejects.toMatchObject({ statusCode: 403, path: '/functions/fixture/runs/create' });
		await expect(rejection).rejects.toThrow('Access denied');
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

	it('keeps streaming past the client request timeout', async () => {
		const shortTimeoutClient = new NotteClient({ baseUrl, apiKey: 'test-key', timeoutMs: 50 }); // pragma: allowlist secret
		handle = (_, res) => {
			res.writeHead(200, { 'content-type': 'text/event-stream' });
			res.write(': heartbeat\n\n');
			setTimeout(() => res.end(event('result', JSON.stringify(finalResult))), 200);
		};
		expect(await shortTimeoutClient.NotteFunction({ function_id: 'fixture' }).run()).toEqual(finalResult);
	});

	it.each([true, false])('aborts with NotteTimeoutError once timeoutMs elapses (stream=%s)', async stream => {
		let close!: () => void;
		const closed = new Promise<void>(resolve => { close = resolve; });
		handle = (_, res) => {
			res.writeHead(200, { 'content-type': stream ? 'text/event-stream' : 'application/json' });
			if (stream) res.write(': heartbeat\n\n');
			res.on('close', close);
		};
		const rejection = client.NotteFunction({ function_id: 'fixture' }).run({}, { stream, timeoutMs: 50 });
		await expect(rejection).rejects.toBeInstanceOf(NotteTimeoutError);
		await expect(rejection).rejects.toThrow('Function fixture run timed out after 50ms');
		await closed;
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
		['malformed event', 'data: {oops}\n\n', 'Malformed function stream event'],
		['invalid result', event('result', '{}'), 'Invalid function result'],
		['stream error', event('error', 'execution interrupted'), 'execution interrupted'],
	])('rejects %s with NotteError', async (_, payload, error) => {
		handle = (_, res) => res.end(payload);
		const rejection = client.NotteFunction({ function_id: 'fixture' }).run();
		await expect(rejection).rejects.toBeInstanceOf(NotteError);
		await expect(rejection).rejects.toThrow(error);
	});

	it.each([true, false])('surfaces the runtime authentication envelope as NotteAPIError (stream=%s)', async stream => {
		// The execution runtime answers a missing key with its own 401 envelope, relayed as a 200.
		const envelope = { statusCode: 401, headers: { 'Content-Type': 'application/json' }, body: '{"error": "Missing x-notte-api-key header or authorization header", "status": "error"}' };
		handle = (_, res) => {
			res.writeHead(200, { 'content-type': 'application/json' });
			res.end(JSON.stringify(envelope));
		};
		const rejection = client.NotteFunction({ function_id: 'fixture' }).run({}, { stream });
		await expect(rejection).rejects.toBeInstanceOf(NotteAPIError);
		await expect(rejection).rejects.toMatchObject({ statusCode: 401, path: '/functions/fixture/runs/run-1' });
		await expect(rejection).rejects.toThrow('Missing x-notte-api-key header');
	});

	it.each([true, false])('rejects failed executions with FailedToRunCloudFunctionError by default (stream=%s)', async stream => {
		const failure = { ...finalResult, status: 'failed', result: 'boom' };
		handle = (_, res) => res.end(stream ? event('result', JSON.stringify(failure)) : JSON.stringify(failure));
		const rejection = client.NotteFunction({ function_id: 'fixture' }).run({}, { stream });
		await expect(rejection).rejects.toBeInstanceOf(FailedToRunCloudFunctionError);
		await expect(rejection).rejects.toMatchObject({ functionId: 'fixture', functionRunId: 'run-1', response: failure });
		await expect(rejection).rejects.toThrow('Function fixture run run-1 failed');
	});

	it.each([true, false])('can return a failed result without throwing (stream=%s)', async stream => {
		const failure = { ...finalResult, status: 'failed', result: 'boom' };
		handle = (_, res) => res.end(stream ? event('result', JSON.stringify(failure)) : JSON.stringify(failure));
		expect(await client.NotteFunction({ function_id: 'fixture' }).run({}, { stream, raiseOnFailure: false })).toEqual(failure);
	});

	it('rejects a disconnected stream', async () => {
		handle = (_, res) => {
			res.writeHead(200, { 'content-type': 'text/event-stream' });
			res.write(': heartbeat\n\n');
			setImmediate(() => res.destroy());
		};
		await expect(client.NotteFunction({ function_id: 'fixture' }).run()).rejects.toThrow();
	});

	it('propagates HTTP errors of the execution request as NotteAPIError', async () => {
		handle = (_, res) => { res.writeHead(403); res.end(JSON.stringify({ message: 'Access denied' })); };
		const rejection = client.NotteFunction({ function_id: 'fixture' }).run();
		await expect(rejection).rejects.toBeInstanceOf(NotteAPIError);
		await expect(rejection).rejects.toMatchObject({ statusCode: 403, path: '/functions/fixture/runs/run-1' });
		await expect(rejection).rejects.toThrow('Access denied');
	});
});
