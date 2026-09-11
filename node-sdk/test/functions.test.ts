import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { NotteClient } from '@/client';
import { TIMEOUT_HEADER } from '@/client';
import {
	FUNCTION_RUN_ENDPOINTS,
	FUNCTION_RUN_TIMEOUT_MS,
	NotteFunction,
	RUN_API_KEY_HEADER,
	type FunctionRunResult,
} from '@/functions';
import {
	FailedToRunCloudFunctionError,
	InvalidRequestError,
	NotteAPIError,
	NotteError,
	NotteTimeoutError,
} from '@/errors';

vi.mock('@/lib/client/sdk.gen', () => ({
	functionCreate: vi.fn(),
	functionDelete: vi.fn(),
	functionDownloadUrl: vi.fn(),
	functionMetadataUpdate: vi.fn(),
	functionRollback: vi.fn(),
	functionRunGetMetadata: vi.fn(),
	functionScheduleDelete: vi.fn(),
	functionScheduleSet: vi.fn(),
	functionUpdate: vi.fn(),
	listFunctionRunsByFunctionId: vi.fn(),
}));

vi.mock('@/version', () => ({
	SDK_VERSION: '1.0.0',
}));

import {
	functionCreate,
	functionDelete,
	functionDownloadUrl,
	functionMetadataUpdate,
	functionRollback,
	functionRunGetMetadata,
	functionScheduleDelete,
	functionScheduleSet,
	functionUpdate,
	listFunctionRunsByFunctionId,
} from '@/lib/client/sdk.gen';

const FUNCTION_ID = '9fb6d40e-c76a-4d44-a73a-aa7843f0f535';
const API_KEY = 'test-api-key'; // pragma: allowlist secret
// Produced by the python SDK: Encryption(root_key=DECRYPTION_KEY).encrypt(DECRYPTED_URL)
const DECRYPTION_KEY = 'public-sdk-test-key'; // pragma: allowlist secret
const DECRYPTED_URL = 'https://example.com/function.py?signature=test';
const ENCRYPTED_URL =
	'qWKF5mcl2_w6hv6qHgdIi2dBQUFBQUJxbzlpRElXZlhzUHYzNEV3SGVqSDQ1MjRVMkNUcGx6Z3ZnMDlLdmhMWEx6YXY5Sk0zTzZIMWgxT0tUYmhfM0JRWW9RbE1uYUlOOEhRc0FiTXBvWXRraTZkUmd6WHR1eXcwbERnR3o0UDI3X2xlSWRFa1l5bUtsSW4yOGdrdkk0dE9BZXRU'; // pragma: allowlist secret
const PLAIN_URL = 'https://files.us-script.notte.cc/tenant/function/v1.py?signature=plain';
const SCRIPT = 'def run(value: str) -> dict:\n    return {"echo": value}\n';

const post = vi.fn();
const generatedClient = { post };
const mockClient = {
	getClient: () => generatedClient,
	getConfig: () => ({ apiKey: API_KEY, baseUrl: 'https://api.notte.cc' }),
} as unknown as NotteClient;
// A proxy-mode client holds no key: the proxy adds the credentials upstream.
const proxyClient = {
	getClient: () => generatedClient,
	getConfig: () => ({ baseUrl: '/api/notte' }),
} as unknown as NotteClient;

const functionResponse = {
	function_id: FUNCTION_ID,
	created_at: '2026-01-01T00:00:00Z',
	updated_at: '2026-01-01T00:00:00Z',
	latest_version: 'v2',
	versions: ['v1', 'v2'],
	status: 'active',
	workflow_id: FUNCTION_ID,
};
const runResult: FunctionRunResult = {
	function_id: FUNCTION_ID,
	function_run_id: 'run-1',
	session_id: null,
	status: 'closed',
	result: { echo: 'value' },
};

function resolved<T>(data: T) {
	return { data, request: {} as Request, response: {} as Response };
}

function mockDownloadUrl(url: string) {
	vi.mocked(functionDownloadUrl).mockResolvedValue(resolved({ ...functionResponse, url }) as never);
}

function mockRunList() {
	const page = { items: [], page: 1, page_size: 10, has_next: false, has_previous: false };
	vi.mocked(listFunctionRunsByFunctionId).mockResolvedValue(resolved(page) as never);
	return page;
}

function queryOf(mock: typeof listFunctionRunsByFunctionId) {
	return vi.mocked(mock).mock.calls[0]![0].query;
}

function mockFetch(options: { ok: boolean; text?: string; status?: number; statusText?: string }) {
	const fetchMock = vi.fn().mockResolvedValue({
		ok: options.ok,
		status: options.status ?? 200,
		statusText: options.statusText ?? 'OK',
		text: async () => options.text ?? '',
	});
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

function sseStream(...frames: string[]): ReadableStream<Uint8Array> {
	const encoder = new TextEncoder();
	return new ReadableStream({
		start(controller) {
			for (const frame of frames) controller.enqueue(encoder.encode(frame));
			controller.close();
		},
	});
}

const event = (type: string, message: unknown) => `data: ${JSON.stringify({ type, message })}\n\n`;

function writeScript(content = SCRIPT, name = 'echo.py'): { dir: string; path: string } {
	const dir = mkdtempSync(join(tmpdir(), 'notte-function-'));
	const path = join(dir, name);
	writeFileSync(path, content);
	return { dir, path };
}

describe('NotteFunction', () => {
	let fn: NotteFunction;

	beforeEach(() => {
		vi.clearAllMocks();
		vi.spyOn(console, 'info').mockImplementation(() => {});
		fn = new NotteFunction(mockClient, { function_id: FUNCTION_ID, decryption_key: DECRYPTION_KEY });
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	describe('constructor', () => {
		it('exposes the function ID and decryption key immediately', () => {
			expect(fn.getFunctionId()).toBe(FUNCTION_ID);
			expect(fn.functionId).toBe(FUNCTION_ID);
			expect(fn.decryptionKey).toBe(DECRYPTION_KEY);
		});

		it('creates a function without a decryption key', () => {
			const keyless = new NotteFunction(mockClient, { function_id: 'function-without-key' });
			expect(keyless.getFunctionId()).toBe('function-without-key');
			expect(keyless.decryptionKey).toBeUndefined();
		});

		it('rejects an empty function ID', () => {
			expect(() => new NotteFunction(mockClient, { function_id: '' })).toThrow(InvalidRequestError);
		});

		it('rejects a creation path that is not a python file', () => {
			expect(() => new NotteFunction(mockClient, { path: 'script.txt' })).toThrow(
				"Code file path must end with .py, got 'script.txt'",
			);
			expect(() => new NotteFunction(mockClient, { path: 'script.txt' })).toThrow(InvalidRequestError);
		});

		it('rejects options that name neither a function ID nor a path', () => {
			expect(() => new NotteFunction(mockClient, {} as never)).toThrow(InvalidRequestError);
		});
	});

	describe('lazy creation', () => {
		let script: { dir: string; path: string };

		beforeEach(() => {
			script = writeScript();
			vi.mocked(functionCreate).mockResolvedValue(resolved(functionResponse) as never);
		});

		afterEach(() => {
			rmSync(script.dir, { recursive: true, force: true });
		});

		it('does not upload anything until an operation needs the ID', () => {
			const created = new NotteFunction(mockClient, { path: script.path, name: 'Echo' });
			expect(functionCreate).not.toHaveBeenCalled();
			expect(() => created.functionId).toThrow(InvalidRequestError);
			expect(() => created.getFunctionId()).toThrow('Function not initialized');
		});

		it('uploads the python file as multipart form fields, once, before the first operation', async () => {
			const created = new NotteFunction(mockClient, {
				path: script.path,
				name: 'Echo',
				description: 'Echoes its input',
				shared: true,
			});
			mockRunList();

			await Promise.all([created.runs(), created.runs()]);

			expect(functionCreate).toHaveBeenCalledOnce();
			const call = vi.mocked(functionCreate).mock.calls[0]![0];
			expect(call.client).toBe(generatedClient);
			expect(call.body.name).toBe('Echo');
			expect(call.body.description).toBe('Echoes its input');
			expect(call.body.shared).toBe(true);
			expect(call.body.file).toBeInstanceOf(File);
			expect((call.body.file as File).name).toBe('echo.py');
			expect(await (call.body.file as File).text()).toBe(SCRIPT);
			expect(created.functionId).toBe(FUNCTION_ID);
			expect(created.getFunctionId()).toBe(FUNCTION_ID);
			expect(listFunctionRunsByFunctionId).toHaveBeenCalledWith(
				expect.objectContaining({ path: { function_id: FUNCTION_ID } }),
			);
		});

		it('omits optional metadata that was not provided', async () => {
			const created = new NotteFunction(mockClient, { path: script.path });
			mockRunList();

			await created.runs();

			const body = vi.mocked(functionCreate).mock.calls[0]![0].body;
			expect(body.name).toBeUndefined();
			expect(body.description).toBeUndefined();
			expect(body.shared).toBeUndefined();
		});

		it('keeps the decryption key given at creation time', async () => {
			const created = new NotteFunction(mockClient, { path: script.path, decryption_key: DECRYPTION_KEY });
			mockDownloadUrl(ENCRYPTED_URL);

			await expect(created.getUrl()).resolves.toBe(DECRYPTED_URL);
			expect(created.decryptionKey).toBe(DECRYPTION_KEY);
		});

		it('rejects when the file does not exist', async () => {
			const created = new NotteFunction(mockClient, { path: join(script.dir, 'missing.py') });

			await expect(created.get()).rejects.toThrow(InvalidRequestError);
			expect(functionCreate).not.toHaveBeenCalled();
		});

		it('propagates API failures of the upload', async () => {
			const error = new NotteAPIError('/functions', 422, { message: "Python script must contain a 'run' function" });
			vi.mocked(functionCreate).mockRejectedValue(error);
			const created = new NotteFunction(mockClient, { path: script.path });

			await expect(created.get()).rejects.toBe(error);
			await expect(created.get()).rejects.toBe(error);
			expect(functionCreate).toHaveBeenCalledOnce();
			expect(() => created.functionId).toThrow(InvalidRequestError);
		});
	});

	describe('get', () => {
		it('calls GET /functions/{function_id} and returns the response', async () => {
			mockDownloadUrl(PLAIN_URL);

			await expect(fn.get()).resolves.toEqual({ ...functionResponse, url: PLAIN_URL });
			expect(functionDownloadUrl).toHaveBeenCalledWith({
				client: generatedClient,
				throwOnError: true,
				path: { function_id: FUNCTION_ID },
				query: {},
			});
		});

		it('forwards the requested version', async () => {
			mockDownloadUrl(PLAIN_URL);

			await fn.get({ version: 'v1' });

			expect(functionDownloadUrl).toHaveBeenCalledWith(expect.objectContaining({ query: { version: 'v1' } }));
		});
	});

	describe('update', () => {
		let script: { dir: string; path: string };

		beforeEach(() => {
			script = writeScript('def run(value: str) -> dict:\n    return {"echo": value, "updated": True}\n', 'updated.py');
			vi.mocked(functionUpdate).mockResolvedValue(resolved(functionResponse) as never);
		});

		afterEach(() => {
			rmSync(script.dir, { recursive: true, force: true });
		});

		it('uploads the new code with restricted=true by default', async () => {
			await expect(fn.update({ path: script.path })).resolves.toEqual(functionResponse);

			const call = vi.mocked(functionUpdate).mock.calls[0]![0];
			expect(call.client).toBe(generatedClient);
			expect(call.path).toEqual({ function_id: FUNCTION_ID });
			expect(call.query).toEqual({ restricted: true });
			expect((call.body.file as File).name).toBe('updated.py');
			expect(await (call.body.file as File).text()).toContain('"updated": True');
		});

		it('forwards version and restricted', async () => {
			await fn.update({ path: script.path, version: 'v1', restricted: false });

			expect(functionUpdate).toHaveBeenCalledWith(
				expect.objectContaining({ query: { restricted: false, version: 'v1' } }),
			);
		});

		it('requires a path', async () => {
			await expect(fn.update({})).rejects.toThrow(InvalidRequestError);
			expect(functionUpdate).not.toHaveBeenCalled();
		});

		it('rejects a path that is not a python file', async () => {
			await expect(fn.update({ path: 'script.txt' })).rejects.toThrow("Code file path must end with .py, got 'script.txt'");
			expect(functionUpdate).not.toHaveBeenCalled();
		});
	});

	describe('updateMetadata', () => {
		it('calls PATCH /functions/{function_id} with the metadata body', async () => {
			vi.mocked(functionMetadataUpdate).mockResolvedValue(resolved(functionResponse) as never);

			await expect(fn.updateMetadata({ name: 'Echo', default_runtime: 'extended' })).resolves.toEqual(functionResponse);
			expect(functionMetadataUpdate).toHaveBeenCalledWith({
				client: generatedClient,
				throwOnError: true,
				path: { function_id: FUNCTION_ID },
				body: { name: 'Echo', default_runtime: 'extended' },
			});
		});
	});

	describe('delete', () => {
		it('calls DELETE /functions/{function_id}', async () => {
			const response = { status: 'success' as const, message: 'deleted' };
			vi.mocked(functionDelete).mockResolvedValue(resolved(response) as never);

			await expect(fn.delete()).resolves.toEqual(response);
			expect(functionDelete).toHaveBeenCalledWith({
				client: generatedClient,
				throwOnError: true,
				path: { function_id: FUNCTION_ID },
			});
		});

		it('propagates API errors as NotteAPIError', async () => {
			const error = new NotteAPIError(`/functions/${FUNCTION_ID}`, 404, { message: 'Function not found' });
			vi.mocked(functionDelete).mockRejectedValue(error);

			await expect(fn.delete()).rejects.toBe(error);
		});
	});

	describe('schedules and rollback', () => {
		it('sets a schedule with cron and variables', async () => {
			vi.mocked(functionScheduleSet).mockResolvedValue(resolved({ status: 'scheduled' }) as never);

			await expect(fn.setSchedule({ cron: '0 9 * * *', variables: { url: 'https://example.com' } })).resolves.toEqual({
				status: 'scheduled',
			});
			expect(functionScheduleSet).toHaveBeenCalledWith({
				client: generatedClient,
				throwOnError: true,
				path: { function_id: FUNCTION_ID },
				body: { cron: '0 9 * * *', variables: { url: 'https://example.com' } },
			});
		});

		it('sends null variables when the schedule has none', async () => {
			vi.mocked(functionScheduleSet).mockResolvedValue(resolved({ status: 'scheduled' }) as never);

			await fn.setSchedule({ cron: '0 9 * * *' });

			expect(functionScheduleSet).toHaveBeenCalledWith(
				expect.objectContaining({ body: { cron: '0 9 * * *', variables: null } }),
			);
		});

		it('deletes the schedule', async () => {
			vi.mocked(functionScheduleDelete).mockResolvedValue(resolved({ status: 'deleted' }) as never);

			await expect(fn.deleteSchedule()).resolves.toEqual({ status: 'deleted' });
			expect(functionScheduleDelete).toHaveBeenCalledWith({
				client: generatedClient,
				throwOnError: true,
				path: { function_id: FUNCTION_ID },
			});
		});

		it('rolls back to a version with restricted=true by default', async () => {
			vi.mocked(functionRollback).mockResolvedValue(resolved(functionResponse) as never);

			await expect(fn.rollback({ version: 'v1' })).resolves.toEqual(functionResponse);
			expect(functionRollback).toHaveBeenCalledWith({
				client: generatedClient,
				throwOnError: true,
				path: { function_id: FUNCTION_ID },
				query: { restricted: true },
				body: { version: 'v1' },
			});
		});

		it('forwards restricted=false on rollback', async () => {
			vi.mocked(functionRollback).mockResolvedValue(resolved(functionResponse) as never);

			await fn.rollback({ version: 'v1', restricted: false });

			expect(functionRollback).toHaveBeenCalledWith(expect.objectContaining({ query: { restricted: false } }));
		});
	});

	describe('getRun / retrieve', () => {
		const metadata = {
			function_id: FUNCTION_ID,
			function_run_id: 'test-run-id',
			created_at: '2023-01-01T00:00:00Z',
			updated_at: '2023-01-01T00:00:00Z',
			status: 'active' as const,
		};

		it('calls GET /functions/{function_id}/runs/{run_id}', async () => {
			vi.mocked(functionRunGetMetadata).mockResolvedValue(resolved(metadata) as never);

			await expect(fn.getRun('test-run-id')).resolves.toEqual(metadata);
			expect(functionRunGetMetadata).toHaveBeenCalledWith({
				client: generatedClient,
				throwOnError: true,
				path: { function_id: FUNCTION_ID, run_id: 'test-run-id' },
			});
		});

		it('keeps retrieve() as an alias', async () => {
			vi.mocked(functionRunGetMetadata).mockResolvedValue(resolved(metadata) as never);

			await expect(fn.retrieve('test-run-id')).resolves.toEqual(metadata);
		});

		it('propagates API errors as NotteAPIError', async () => {
			const error = new NotteAPIError(`/functions/${FUNCTION_ID}/runs/test-run-id`, 404, { message: 'Run not found' });
			vi.mocked(functionRunGetMetadata).mockRejectedValue(error);

			const rejection = fn.retrieve('test-run-id');
			await expect(rejection).rejects.toBe(error);
			await expect(rejection).rejects.toBeInstanceOf(NotteAPIError);
			await expect(rejection).rejects.toMatchObject({ statusCode: 404 });
		});
	});

	describe('createRun', () => {
		const created = { function_id: FUNCTION_ID, function_run_id: 'run-123', created_at: '2026-01-01T00:00:00Z', status: 'created' as const };

		it('posts to the hand-rolled create endpoint without executing the function', async () => {
			post.mockResolvedValue(resolved(created));

			await expect(fn.createRun()).resolves.toEqual(created);

			expect(post).toHaveBeenCalledOnce();
			expect(post).toHaveBeenCalledWith({
				url: FUNCTION_RUN_ENDPOINTS.create,
				path: { function_id: FUNCTION_ID },
				body: { local: false },
				headers: { 'Content-Type': 'application/json' },
				parseAs: 'json',
				signal: undefined,
				throwOnError: true,
			});
			expect(functionDownloadUrl).not.toHaveBeenCalled();
		});

		it('forwards local=true', async () => {
			post.mockResolvedValue(resolved(created));

			await fn.createRun({ local: true });

			expect(post).toHaveBeenCalledWith(expect.objectContaining({ body: { local: true } }));
		});

		it('executes a created run through the hand-rolled start endpoint without creating another', async () => {
			post.mockResolvedValueOnce(resolved(created)).mockResolvedValueOnce(resolved(runResult));

			const response = await fn.createRun();
			const result = await fn.run({ url: 'https://example.com' }, { functionRunId: response.function_run_id, stream: false });

			expect(result).toEqual(runResult);
			expect(post).toHaveBeenCalledTimes(2);
			expect(post.mock.calls[1]![0]).toEqual({
				url: FUNCTION_RUN_ENDPOINTS.start,
				path: { function_id: FUNCTION_ID, run_id: 'run-123' },
				body: {
					workflow_id: FUNCTION_ID,
					variables: { url: 'https://example.com' },
					stream: false,
					function_run_id: 'run-123',
				},
				headers: { 'Content-Type': 'application/json', [TIMEOUT_HEADER]: '0', [RUN_API_KEY_HEADER]: API_KEY },
				parseAs: 'json',
				signal: expect.any(AbortSignal),
				throwOnError: true,
			});
		});

		it('propagates API errors', async () => {
			const error = new NotteAPIError(`/functions/${FUNCTION_ID}/runs/create`, 403, { message: 'Function unavailable' });
			post.mockRejectedValue(error);

			await expect(fn.createRun()).rejects.toBe(error);
		});
	});

	describe('run', () => {
		const created = { function_id: FUNCTION_ID, function_run_id: 'run-1', created_at: '2026-01-01T00:00:00Z', status: 'created' as const };
		/** `run()` without an ID creates a record first, then executes it: mock both hand-rolled calls. */
		const mockRun = (data: unknown) => post.mockResolvedValueOnce(resolved(created)).mockResolvedValueOnce(resolved(data));
		const startCall = () => post.mock.calls[1]![0];

		it('creates a run record and then executes it, like Python', async () => {
			mockRun(runResult);

			await expect(fn.run({ test: 'test' }, { stream: false })).resolves.toEqual(runResult);

			expect(post).toHaveBeenCalledTimes(2);
			expect(post.mock.calls[0]![0]).toMatchObject({ url: FUNCTION_RUN_ENDPOINTS.create, body: { local: false } });
			expect(startCall()).toEqual({
				url: FUNCTION_RUN_ENDPOINTS.start,
				path: { function_id: FUNCTION_ID, run_id: 'run-1' },
				body: { workflow_id: FUNCTION_ID, variables: { test: 'test' }, stream: false, function_run_id: 'run-1' },
				headers: { 'Content-Type': 'application/json', [TIMEOUT_HEADER]: '0', [RUN_API_KEY_HEADER]: API_KEY },
				parseAs: 'json',
				signal: expect.any(AbortSignal),
				throwOnError: true,
			});
		});

		it('does not create a record when functionRunId is given', async () => {
			post.mockResolvedValueOnce(resolved(runResult));

			await expect(fn.run({}, { functionRunId: 'run-1', stream: false })).resolves.toEqual(runResult);

			expect(post).toHaveBeenCalledOnce();
			expect(post.mock.calls[0]![0]).toMatchObject({ url: FUNCTION_RUN_ENDPOINTS.start, path: { function_id: FUNCTION_ID, run_id: 'run-1' } });
		});

		it('omits the api key header in proxy mode instead of requiring a raw key', async () => {
			const proxied = new NotteFunction(proxyClient, { function_id: FUNCTION_ID });
			mockRun(runResult);

			await expect(proxied.run({}, { stream: false })).resolves.toEqual(runResult);

			expect(startCall().headers).toEqual({ 'Content-Type': 'application/json', [TIMEOUT_HEADER]: '0' });
		});

		it('streams by default and reports logs through onLog', async () => {
			mockRun(sseStream(event('log', 'hello'), event('session_start', 'session-1'), event('result', JSON.stringify(runResult))));
			const onLog = vi.fn();

			await expect(fn.run({}, { onLog })).resolves.toEqual(runResult);

			expect(startCall().parseAs).toBe('stream');
			expect(startCall().body.stream).toBe(true);
			expect(onLog).toHaveBeenCalledWith('hello');
		});

		it.each([undefined, 'standard', 'extended'] as const)('forwards runtime=%s outside the script variables', async runtime => {
			mockRun(runResult);

			await fn.run({ runtime: 'script-input', wait_seconds: 960 }, { runtime, stream: false });

			const body = startCall().body;
			expect(body.variables).toEqual({ runtime: 'script-input', wait_seconds: 960 });
			if (runtime === undefined) {
				expect(body).not.toHaveProperty('runtime');
			} else {
				expect(body.runtime).toBe(runtime);
			}
		});

		it('rejects an invalid runtime before creating a run', async () => {
			await expect(fn.run({}, { runtime: 'invalid' as never })).rejects.toThrow(InvalidRequestError);
			expect(post).not.toHaveBeenCalled();
		});

		it('rejects a non-positive timeout before creating a run', async () => {
			await expect(fn.run({}, { timeoutMs: 0 })).rejects.toThrow(InvalidRequestError);
			expect(post).not.toHaveBeenCalled();
		});

		it('throws FailedToRunCloudFunctionError when the run failed', async () => {
			const failure = { ...runResult, status: 'failed' as const, result: 'boom' };
			mockRun(failure);

			const rejection = fn.run({}, { stream: false });
			await expect(rejection).rejects.toBeInstanceOf(FailedToRunCloudFunctionError);
			await expect(rejection).rejects.toMatchObject({
				functionId: FUNCTION_ID,
				functionRunId: 'run-1',
				response: failure,
			});
			await expect(rejection).rejects.toThrow(`Function ${FUNCTION_ID} run run-1 failed`);
		});

		it('returns a failed run when raiseOnFailure is false', async () => {
			const failure = { ...runResult, status: 'failed' as const, result: 'boom' };
			mockRun(sseStream(event('result', JSON.stringify(failure))));

			await expect(fn.run({}, { raiseOnFailure: false })).resolves.toEqual(failure);
		});

		it('rejects a non-streaming response that is not a function run result', async () => {
			mockRun('function-run-response');

			await expect(fn.run({}, { stream: false })).rejects.toThrow(NotteError);
		});

		it.each([true, false])('surfaces the runtime authentication envelope as NotteAPIError (stream=%s)', async stream => {
			const envelope = JSON.stringify({
				statusCode: 401,
				headers: { 'Content-Type': 'application/json' },
				body: '{"error": "Missing x-notte-api-key header or authorization header", "status": "error"}',
			});
			mockRun(stream ? sseStream(envelope) : JSON.parse(envelope));

			const rejection = fn.run({}, { stream });
			await expect(rejection).rejects.toBeInstanceOf(NotteAPIError);
			await expect(rejection).rejects.toMatchObject({
				statusCode: 401,
				path: `/functions/${FUNCTION_ID}/runs/run-1`,
				error: { error: 'Missing x-notte-api-key header or authorization header', status: 'error' },
			});
		});

		it('rejects a stream that ends without a result', async () => {
			mockRun(sseStream(': heartbeat\n\n'));

			await expect(fn.run()).rejects.toThrow('Function stream ended without a result');
		});

		it('rejects a stream error event', async () => {
			mockRun(sseStream(event('error', 'execution interrupted')));

			await expect(fn.run()).rejects.toThrow('Function stream error: execution interrupted');
		});

		it('propagates API errors as NotteAPIError', async () => {
			const error = new NotteAPIError(`/functions/${FUNCTION_ID}/runs/run-1`, 404, { message: 'Function not found' });
			post.mockResolvedValueOnce(resolved(created)).mockRejectedValueOnce(error);

			await expect(fn.run()).rejects.toBe(error);
		});

		it('aborts the wait with NotteTimeoutError once timeoutMs elapses', async () => {
			let cancelled = false;
			const neverEnding = new ReadableStream<Uint8Array>({
				cancel() {
					cancelled = true;
				},
			});
			mockRun(neverEnding);

			const rejection = fn.run({}, { timeoutMs: 20 });
			await expect(rejection).rejects.toBeInstanceOf(NotteTimeoutError);
			await expect(rejection).rejects.toThrow('timed out after 20ms');
			expect(cancelled).toBe(true);
			expect(startCall().signal.aborted).toBe(true);
		});

		it('defaults the deadline to five minutes like Python', () => {
			expect(FUNCTION_RUN_TIMEOUT_MS).toBe(300_000);
		});
	});

	describe('result serialization', () => {
		const created = { function_id: FUNCTION_ID, function_run_id: 'run-1', created_at: '2026-01-01T00:00:00Z', status: 'created' as const };
		const mockRun = (data: unknown) => post.mockResolvedValueOnce(resolved(created)).mockResolvedValueOnce(resolved(data));

		it('normalizes a missing session_id to null and keeps structured results', async () => {
			const payload = { function_id: FUNCTION_ID, function_run_id: 'run-1', status: 'closed', result: { use_cases: [{ id: '1', slug: 'hipcamp' }] } };
			mockRun(payload);

			await expect(fn.run({}, { stream: false })).resolves.toEqual({ ...payload, session_id: null });
		});

		it('drops legacy workflow aliases from the backend response', async () => {
			mockRun({ ...runResult, workflow_id: FUNCTION_ID, workflow_run_id: 'run-1' });

			await expect(fn.run({}, { stream: false })).resolves.toEqual(runResult);
		});

		it('decodes the JSON-encoded result frame of a stream', async () => {
			const payload = { ...runResult, session_id: 'session-1', result: [{ id: '1', slug: 'a' }, { id: '2', slug: 'b' }] };
			mockRun(sseStream(event('result', JSON.stringify(payload))));

			await expect(fn.run()).resolves.toEqual(payload);
		});

		it('keeps a string result unchanged', async () => {
			const payload = { ...runResult, result: 'already a string' };
			mockRun(sseStream(event('result', payload)));

			await expect(fn.run()).resolves.toEqual(payload);
		});

		it('rejects a result frame with an unknown status', async () => {
			mockRun(sseStream(event('result', JSON.stringify({ ...runResult, status: 'unknown' }))));

			await expect(fn.run()).rejects.toThrow('Invalid function result');
		});
	});

	describe('getUrl', () => {
		it('reads the url field of the response', async () => {
			mockDownloadUrl(PLAIN_URL);

			await expect(fn.getUrl()).resolves.toBe(PLAIN_URL);
			expect(functionDownloadUrl).toHaveBeenCalledWith(
				expect.objectContaining({ path: { function_id: FUNCTION_ID }, query: {} }),
			);
		});

		it('forwards the requested version', async () => {
			mockDownloadUrl(PLAIN_URL);

			await fn.getUrl({ version: 'v1.0.0' });

			expect(functionDownloadUrl).toHaveBeenCalledWith(expect.objectContaining({ query: { version: 'v1.0.0' } }));
		});

		it('decrypts an encrypted url with the constructor key', async () => {
			mockDownloadUrl(ENCRYPTED_URL);

			await expect(fn.getUrl()).resolves.toBe(DECRYPTED_URL);
		});

		it('decrypts an encrypted url with a per-call key', async () => {
			mockDownloadUrl(ENCRYPTED_URL);
			const keyless = new NotteFunction(mockClient, { function_id: 'fn-id' });

			await expect(keyless.getUrl({ decryption_key: DECRYPTION_KEY })).resolves.toBe(DECRYPTED_URL);
		});

		it('throws InvalidRequestError when an encrypted url has no decryption key', async () => {
			mockDownloadUrl(ENCRYPTED_URL);
			const keyless = new NotteFunction(mockClient, { function_id: 'fn-id' });

			const rejection = keyless.getUrl();
			await expect(rejection).rejects.toBeInstanceOf(InvalidRequestError);
			await expect(rejection).rejects.toThrow('Decryption key is required');
		});

		it('throws InvalidRequestError when the decryption key is wrong', async () => {
			mockDownloadUrl(ENCRYPTED_URL);

			const rejection = fn.getUrl({ decryption_key: 'wrong-key' });
			await expect(rejection).rejects.toBeInstanceOf(InvalidRequestError);
			await expect(rejection).rejects.toThrow('Failed to decrypt the function download url');
		});

		it('propagates API errors as NotteAPIError', async () => {
			const error = new NotteAPIError(`/functions/${FUNCTION_ID}`, 404, { message: 'Function not found' });
			vi.mocked(functionDownloadUrl).mockRejectedValue(error);

			await expect(fn.getUrl()).rejects.toBe(error);
		});
	});

	describe('download', () => {
		it('returns the downloaded code', async () => {
			mockDownloadUrl(PLAIN_URL);
			const fetchMock = mockFetch({ ok: true, text: SCRIPT });

			await expect(fn.download()).resolves.toBe(SCRIPT);
			expect(fetchMock).toHaveBeenCalledWith(PLAIN_URL, expect.anything());
		});

		it('writes the code to the given path', async () => {
			mockDownloadUrl(PLAIN_URL);
			mockFetch({ ok: true, text: SCRIPT });
			const target = join(tmpdir(), `notte-download-${Date.now()}.py`);

			try {
				await expect(fn.download({ path: target })).resolves.toBe(SCRIPT);
				expect(readFileSync(target, 'utf8')).toBe(SCRIPT);
			} finally {
				rmSync(target, { force: true });
			}
		});

		it('rejects a path that is not a python file with InvalidRequestError', async () => {
			mockDownloadUrl(PLAIN_URL);

			const rejection = fn.download({ path: 'invalid_file.txt' });
			await expect(rejection).rejects.toBeInstanceOf(InvalidRequestError);
			await expect(rejection).rejects.toThrow("Code file path must end with .py, got 'invalid_file.txt'");
			expect(functionDownloadUrl).not.toHaveBeenCalled();
		});

		it('throws when the file server returns an error status', async () => {
			mockDownloadUrl(PLAIN_URL);
			mockFetch({ ok: false, status: 403, statusText: 'Forbidden' });

			const rejection = fn.download();
			await expect(rejection).rejects.toBeInstanceOf(NotteError);
			await expect(rejection).rejects.toThrow('Failed to download function code: 403 Forbidden');
		});

		it('does not leak the presigned url when the download fails', async () => {
			mockDownloadUrl(PLAIN_URL);
			vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('socket hang up')));

			await expect(fn.download()).rejects.toThrow('socket hang up');
			await expect(fn.download()).rejects.not.toThrow(PLAIN_URL);
		});
	});

	describe('runs', () => {
		// This method sends only_active=false explicitly instead of relying on the
		// endpoint default, so a finished function is never answered with an empty
		// list - including on API versions that predate the server-side default
		// flipping to false. Keep these two assertions.
		it('asks for every run, not just the active ones, by default', async () => {
			mockRunList();

			await fn.runs();

			expect(queryOf(listFunctionRunsByFunctionId)).toEqual({ only_active: false });
		});

		it('lets the caller opt back in to active-only runs', async () => {
			mockRunList();

			await fn.runs({ only_active: true });

			expect(queryOf(listFunctionRunsByFunctionId)).toEqual({ only_active: true });
		});

		it('returns the paginated response and targets the function', async () => {
			const page = mockRunList();

			await expect(fn.runs()).resolves.toEqual(page);
			expect(listFunctionRunsByFunctionId).toHaveBeenCalledWith(
				expect.objectContaining({ client: generatedClient, path: { function_id: FUNCTION_ID } }),
			);
		});

		it('forwards pagination and filter options', async () => {
			mockRunList();

			await fn.runs({ page: 3, page_size: 50, only_current_token: true, include_system: false });

			expect(queryOf(listFunctionRunsByFunctionId)).toEqual({
				page: 3,
				page_size: 50,
				only_active: false,
				only_current_token: true,
				include_system: false,
			});
		});

		it('keeps the false default when only_active is passed as undefined', async () => {
			mockRunList();

			await fn.runs({ only_active: undefined });

			expect(queryOf(listFunctionRunsByFunctionId)).toEqual({ only_active: false });
		});

		it('propagates API errors as NotteAPIError', async () => {
			const error = new NotteAPIError(`/functions/${FUNCTION_ID}/runs`, 404, { message: 'Function not found' });
			vi.mocked(listFunctionRunsByFunctionId).mockRejectedValue(error);

			await expect(fn.runs()).rejects.toBe(error);
		});
	});
});
