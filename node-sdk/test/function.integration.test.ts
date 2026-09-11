/**
 * Live lifecycle of a function owned by this file, mirroring
 * `tests/integration/sdk/test_workflows.py` and `test_workflow_runs.py`:
 * create from a temp `.py` -> get -> list -> update -> download -> runs -> delete.
 * No `NOTTE_FUNCTION_ID`; the browser-free echo script needs no session.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { config } from 'dotenv';
import { NotteClient } from '@/client';
import { NotteFunction } from '@/functions';
import { InvalidRequestError, NotteAPIError } from '@/errors';
import { functionRunStop } from '@/lib/client/sdk.gen';

config();

const SCRIPT = 'def run(value: str) -> dict:\n    return {"echo": value}\n';
const UPDATED_SCRIPT = 'def run(value: str) -> dict:\n    return {"echo": value, "updated": True}\n';

describe('Function live integration', () => {
	let client: NotteClient;
	let fn: NotteFunction;
	let dir: string;
	let scriptPath: string;
	let updatedPath: string;

	beforeAll(async () => {
		client = new NotteClient();
		dir = mkdtempSync(join(tmpdir(), 'notte-function-'));
		scriptPath = join(dir, 'echo_function.py');
		updatedPath = join(dir, 'echo_function_updated.py');
		writeFileSync(scriptPath, SCRIPT);
		writeFileSync(updatedPath, UPDATED_SCRIPT);
		fn = client.NotteFunction({ path: scriptPath, name: `node-sdk-${Date.now()}`, description: 'Node SDK live fixture' });
		expect(() => fn.functionId).toThrow(InvalidRequestError);
		const created = await fn.get();
		expect(created.function_id).toBe(fn.functionId);
	}, 60000);

	afterAll(async () => {
		try {
			if (fn) {
				const deleted = await fn.delete();
				expect(deleted.status).toBe('success');
			}
		} finally {
			rmSync(dir, { recursive: true, force: true });
		}
	}, 60000);

	it('creates the function lazily from the python file', async () => {
		const response = await fn.get();
		expect(response.function_id).toBe(fn.getFunctionId());
		expect(response.latest_version).toBeTruthy();
		expect(response.status).toBeTruthy();
		expect(response.url).toMatch(/^https?:\/\//);
		expect(response.name).toMatch(/^node-sdk-/);
	});

	it('appears in the functions list', async () => {
		const items = await client.functions.list({ page_size: 50 });
		expect(items.map(item => item.function_id)).toContain(fn.functionId);
	});

	it('references the same function by ID', async () => {
		const byId = client.NotteFunction({ function_id: fn.functionId });
		expect(byId.functionId).toBe(fn.functionId);
		const response = await byId.get();
		expect(response.function_id).toBe(fn.functionId);
	});

	it('updates the code with a modified script and bumps the version', async () => {
		const before = await fn.get();
		// Server-generated versions have second precision; create and update can
		// happen within the same second on CI. Exercise a distinct explicit version.
		const version = `node-sdk-update-${Date.now()}`;
		const updated = await fn.update({ path: updatedPath, version });
		expect(updated.latest_version).toBe(version);
		expect(updated.function_id).toBe(fn.functionId);
		expect(updated.latest_version).toBeTruthy();
		expect(updated.latest_version).not.toBe(before.latest_version);
		expect(updated.versions).toContain(before.latest_version);
		await expect(fn.download()).resolves.toContain('"updated": True');
	});

	it('updates the metadata', async () => {
		const updated = await fn.updateMetadata({ description: 'Node SDK live fixture (updated)' });
		expect(updated.description).toBe('Node SDK live fixture (updated)');
	});

	it('exposes a download url and the code', async () => {
		const url = await fn.getUrl();
		expect(url).toMatch(/^https?:\/\//);
		const code = await fn.download();
		expect(code).toContain('def run(value: str)');
	});

	it('downloads the code to a python file', async () => {
		const target = join(dir, 'downloaded.py');
		const code = await fn.download({ path: target });
		expect(readFileSync(target, 'utf8')).toBe(code);
	});

	it('rejects a download path that is not a python file', async () => {
		await expect(fn.download({ path: join(dir, 'invalid_file.txt') })).rejects.toThrow(InvalidRequestError);
	});

	it('creates, executes, retrieves and lists runs', { timeout: 180000 }, async () => {
		const created = await fn.createRun();
		expect(created.function_id).toBe(fn.functionId);
		expect(created.status).toBe('created');
		try {
			const before = await fn.getRun(created.function_run_id);
			expect(before.status).toBe('active');
			expect(before.result).toBeNull();

			const value = `node-sdk-${Date.now()}`;
			const result = await fn.run({ value }, { functionRunId: created.function_run_id });
			expect(result.function_run_id).toBe(created.function_run_id);
			expect(result.status).toBe('closed');
			expect(result.result).toEqual({ echo: value, updated: true });

			const persisted = await fn.getRun(created.function_run_id);
			expect(persisted.status).toBe('closed');
			expect(persisted.variables).toEqual({ value });

			const page = await fn.runs({ page_size: 10 });
			expect(page.page).toBe(1);
			expect(page.page_size).toBe(10);
			expect(page.items.map(item => item.function_run_id)).toContain(created.function_run_id);
			const listed = page.items.find(item => item.function_run_id === created.function_run_id)!;
			expect(listed.function_id).toBe(fn.functionId);
			expect(listed).not.toHaveProperty('logs');
			expect(listed).not.toHaveProperty('result');
		} finally {
			if ((await fn.getRun(created.function_run_id)).status === 'active') {
				await functionRunStop({ client: client.getClient(), path: { function_id: fn.functionId, run_id: created.function_run_id }, throwOnError: true });
			}
		}
	});

	it('runs without a pre-created record, with and without streaming', { timeout: 180000 }, async () => {
		const logs: string[] = [];
		const streamed = await fn.run({ value: 'streamed' }, { onLog: line => logs.push(line) });
		expect(streamed.status).toBe('closed');
		expect(streamed.result).toEqual({ echo: 'streamed', updated: true });

		const plain = await fn.run({ value: 'plain' }, { stream: false });
		expect(plain.status).toBe('closed');
		expect(plain.result).toEqual({ echo: 'plain', updated: true });
		expect(plain.function_run_id).not.toBe(streamed.function_run_id);
	});

	it('rejects a run for an unknown run ID with NotteAPIError', { timeout: 60000 }, async () => {
		await expect(fn.run({ value: 'x' }, { functionRunId: 'invalid-run-id', stream: false })).rejects.toBeInstanceOf(NotteAPIError);
	});
});
