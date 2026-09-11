/**
 * Pins the HTTP paths and methods the function wrapper uses, mirroring
 * `tests/sdk/test_function_endpoint_paths.py`. Every request goes through the
 * real generated client against a recording fetch, so a regenerated client or
 * a refactor of the hand-rolled run endpoints cannot silently move a call to
 * `/workflows/` or to a different method.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';
import { FUNCTION_RUN_ENDPOINTS, NotteFunction } from '@/functions';
import type { FunctionCreateData, FunctionUpdateData } from '@/lib/client/types.gen';

const FUNCTION_ID = 'function-123';
const RUN_ID = 'run-123';
const BASE_URL = 'https://api.notte.cc';

const functionResponse = {
	function_id: FUNCTION_ID,
	created_at: '2026-01-01T00:00:00Z',
	updated_at: '2026-01-01T00:00:00Z',
	latest_version: 'v1',
	versions: ['v1'],
	status: 'active',
	url: 'https://files.example.com/function.py',
};
const runResult = { function_id: FUNCTION_ID, function_run_id: RUN_ID, session_id: null, status: 'closed', result: {} };

type Recorded = { method: string; path: string; body: unknown; headers: Headers };

describe('function endpoint paths', () => {
	const calls: Recorded[] = [];
	let fn: NotteFunction;
	let responses: unknown[];

	beforeEach(() => {
		calls.length = 0;
		responses = [];
		const fetch = vi.fn<typeof globalThis.fetch>(async input => {
			const request = input instanceof Request ? input : new Request(input);
			const contentType = request.headers.get('content-type') ?? '';
			let body: unknown;
			if (contentType.startsWith('multipart/form-data')) {
				const fields: Record<string, FormDataEntryValue> = {};
				(await request.formData()).forEach((value, key) => { fields[key] = value; });
				body = fields;
			} else {
				body = contentType.includes('json') ? await request.json() : await request.text();
			}
			calls.push({ method: request.method, path: new URL(request.url).pathname + new URL(request.url).search, body, headers: request.headers });
			return Response.json(responses.shift() ?? {});
		});
		const client = new NotteClient({ apiKey: 'test-api-key', baseUrl: BASE_URL }); // pragma: allowlist secret
		client.getClient().setConfig({ fetch });
		fn = client.NotteFunction({ function_id: FUNCTION_ID });
	});

	it('exposes the hand-rolled run endpoints under /functions', () => {
		expect(FUNCTION_RUN_ENDPOINTS).toEqual({
			create: '/functions/{function_id}/runs/create',
			start: '/functions/{function_id}/runs/{run_id}',
		});
		const create: FunctionCreateData['url'] = '/functions';
		const update: FunctionUpdateData['url'] = '/functions/{function_id}';
		expect([...Object.values(FUNCTION_RUN_ENDPOINTS), create, update].some(url => url.includes('/workflows/'))).toBe(false);
	});

	it('createRun posts to /functions/{id}/runs/create', async () => {
		responses.push({ function_id: FUNCTION_ID, function_run_id: RUN_ID, created_at: '2026-01-01T00:00:00Z', status: 'created' });

		await fn.createRun();

		expect(calls).toEqual([
			expect.objectContaining({ method: 'POST', path: `/functions/${FUNCTION_ID}/runs/create`, body: { local: false } }),
		]);
	});

	it('run with a run ID posts to /functions/{id}/runs/{run_id}', async () => {
		responses.push(runResult);

		await fn.run({ query: 'hello' }, { functionRunId: RUN_ID, stream: false });

		expect(calls).toEqual([
			expect.objectContaining({
				method: 'POST',
				path: `/functions/${FUNCTION_ID}/runs/${RUN_ID}`,
				body: { workflow_id: FUNCTION_ID, variables: { query: 'hello' }, stream: false, function_run_id: RUN_ID },
			}),
		]);
	});

	it('run without a run ID creates a record then posts to /functions/{id}/runs/{run_id}, like Python', async () => {
		responses.push({ function_id: FUNCTION_ID, function_run_id: RUN_ID, created_at: '2026-01-01T00:00:00Z', status: 'created' }, runResult);

		await fn.run({ query: 'hello' }, { stream: false });

		expect(calls).toEqual([
			expect.objectContaining({ method: 'POST', path: `/functions/${FUNCTION_ID}/runs/create`, body: { local: false } }),
			expect.objectContaining({
				method: 'POST',
				path: `/functions/${FUNCTION_ID}/runs/${RUN_ID}`,
				body: { workflow_id: FUNCTION_ID, variables: { query: 'hello' }, stream: false, function_run_id: RUN_ID },
			}),
		]);
		expect(calls.every(call => !call.path.includes('/runs/start'))).toBe(true);
	});

	it('run sends the bearer token and hands the key to the runtime through x-notte-api-key', async () => {
		responses.push({ function_id: FUNCTION_ID, function_run_id: RUN_ID, created_at: '2026-01-01T00:00:00Z', status: 'created' }, runResult, runResult);

		await fn.run({}, { stream: false });
		await fn.run({}, { functionRunId: RUN_ID, stream: false });

		expect(calls).toHaveLength(3);
		for (const call of calls) {
			expect(call.headers.get('authorization')).toBe('Bearer test-api-key');
			expect(call.headers.has('x-notte-timeout-ms')).toBe(false);
		}
		const [create, ...starts] = calls;
		expect(create!.headers.has('x-notte-api-key')).toBe(false);
		for (const start of starts) {
			expect(start.headers.get('x-notte-api-key')).toBe('test-api-key');
		}
	});

	it('run in proxy mode omits x-notte-api-key rather than failing without a key', async () => {
		responses.push({ function_id: FUNCTION_ID, function_run_id: RUN_ID, created_at: '2026-01-01T00:00:00Z', status: 'created' }, runResult);
		const proxyClient = new NotteClient({ baseUrl: '/api/notte' });
		proxyClient.getClient().setConfig({
			baseUrl: BASE_URL,
			fetch: vi.fn<typeof globalThis.fetch>(async input => {
				const request = input instanceof Request ? input : new Request(input);
				calls.push({ method: request.method, path: new URL(request.url).pathname, body: await request.text(), headers: request.headers });
				return Response.json(responses.shift() ?? {});
			}),
		});

		await proxyClient.NotteFunction({ function_id: FUNCTION_ID }).run({}, { stream: false });

		expect(calls.map(call => call.path)).toEqual([`/functions/${FUNCTION_ID}/runs/create`, `/functions/${FUNCTION_ID}/runs/${RUN_ID}`]);
		for (const call of calls) {
			expect(call.headers.has('authorization')).toBe(false);
			expect(call.headers.has('x-notte-api-key')).toBe(false);
		}
	});

	it('getRun gets /functions/{id}/runs/{run_id}', async () => {
		responses.push({ ...runResult, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' });

		await fn.getRun(RUN_ID);

		expect(calls).toEqual([expect.objectContaining({ method: 'GET', path: `/functions/${FUNCTION_ID}/runs/${RUN_ID}` })]);
	});

	it('runs lists /functions/{id}/runs with only_active=false', async () => {
		responses.push({ items: [], page: 1, page_size: 10, has_next: false, has_previous: false });

		await fn.runs();

		expect(calls).toEqual([expect.objectContaining({ method: 'GET', path: `/functions/${FUNCTION_ID}/runs?only_active=false` })]);
	});

	it('get and getUrl read /functions/{id}', async () => {
		responses.push(functionResponse, functionResponse);

		await fn.get();
		await fn.getUrl({ version: 'v1' });

		expect(calls).toEqual([
			expect.objectContaining({ method: 'GET', path: `/functions/${FUNCTION_ID}` }),
			expect.objectContaining({ method: 'GET', path: `/functions/${FUNCTION_ID}?version=v1` }),
		]);
	});

	it('updateMetadata patches /functions/{id}', async () => {
		responses.push(functionResponse);

		await fn.updateMetadata({ name: 'Renamed' });

		expect(calls).toEqual([expect.objectContaining({ method: 'PATCH', path: `/functions/${FUNCTION_ID}`, body: { name: 'Renamed' } })]);
	});

	it('delete deletes /functions/{id}', async () => {
		responses.push({ status: 'success', message: 'deleted' });

		await fn.delete();

		expect(calls).toEqual([expect.objectContaining({ method: 'DELETE', path: `/functions/${FUNCTION_ID}` })]);
	});

	it('schedules use /functions/{id}/schedule and rollback uses /functions/{id}/rollback', async () => {
		responses.push({ status: 'ok' }, { status: 'ok' }, functionResponse);

		await fn.setSchedule({ cron: '0 9 * * *' });
		await fn.deleteSchedule();
		await fn.rollback({ version: 'v1' });

		expect(calls).toEqual([
			expect.objectContaining({ method: 'POST', path: `/functions/${FUNCTION_ID}/schedule`, body: { cron: '0 9 * * *', variables: null } }),
			expect.objectContaining({ method: 'DELETE', path: `/functions/${FUNCTION_ID}/schedule` }),
			expect.objectContaining({ method: 'POST', path: `/functions/${FUNCTION_ID}/rollback?restricted=true`, body: { version: 'v1' } }),
		]);
	});
});
