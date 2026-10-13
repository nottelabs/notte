/**
 * Mirrors `tests/integration/sdk/test_functions.py`: deploy an isolated,
 * browser-free echo function through `client.NotteFunction({ path })`, then
 * exercise createRun -> run -> getRun through the live API without mocks.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { config } from 'dotenv';
import { NotteClient } from '@/client';
import type { NotteFunction } from '@/functions';
import { functionRunStop } from '@/lib/client/sdk.gen';

config();

describe('Function createRun live API integration', () => {
	let client: NotteClient;
	let fn: NotteFunction | undefined;
	let dir: string;

	beforeAll(async () => {
		client = new NotteClient();
		dir = mkdtempSync(join(tmpdir(), 'notte-function-create-run-'));
		const source = join(dir, 'echo_function.py');
		writeFileSync(source, 'def run(value: str) -> dict:\n    return {"echo": value}\n');
		fn = client.NotteFunction({ path: source });
		await fn.get();
	}, 60000);

	afterAll(async () => {
		try {
			if (fn) await fn.delete();
		} finally {
			rmSync(dir, { recursive: true, force: true });
		}
	}, 60000);

	it.each([true, false])('executes and retrieves a pre-created run (stream=%s)', { timeout: 120000 }, async stream => {
		const functionObject = fn!;
		const created = await functionObject.createRun();
		expect(created.function_id).toBe(functionObject.functionId);
		expect(created.status).toBe('created');
		expect(created.function_run_id).toBeTruthy();
		try {
			// Creation alone must leave the run unexecuted.
			const before = await functionObject.getRun(created.function_run_id);
			expect(before.function_run_id).toBe(created.function_run_id);
			expect(before.result).toBeNull();
			expect(before.local).toBe(false);

			const variables = { value: randomUUID() };
			const result = await functionObject.run(variables, { functionRunId: created.function_run_id, stream });
			expect(result.function_run_id).toBe(created.function_run_id);
			expect(result.function_id).toBe(functionObject.functionId);
			expect(result.status).toBe('closed');
			expect(result.result).toEqual({ echo: variables.value });

			const persisted = await functionObject.getRun(created.function_run_id);
			expect(persisted.function_run_id).toBe(created.function_run_id);
			expect(persisted.status).toBe('closed');
			expect(persisted.variables).toEqual(variables);
			expect(JSON.parse(persisted.result!)).toEqual({ echo: variables.value });
			expect(await functionObject.retrieve(created.function_run_id)).toEqual(persisted);
		} finally {
			// Close an unstarted or interrupted run if an earlier assertion failed.
			if ((await functionObject.getRun(created.function_run_id)).status === 'active') {
				await functionRunStop({ client: client.getClient(), path: { function_id: functionObject.functionId, run_id: created.function_run_id }, throwOnError: true });
			}
		}
	});
});
