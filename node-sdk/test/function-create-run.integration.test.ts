import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { config } from 'dotenv';
import { NotteClient } from '@/client';
import type { NotteFunction } from '@/functions';
import { functionCreate, functionDelete, functionRunStop } from '@/lib/client/sdk.gen';

config();

describe('Function createRun live API integration', () => {
	let client: NotteClient;
	let fn: NotteFunction | undefined;

	beforeAll(async () => {
		client = new NotteClient();
		const created = await functionCreate({
			client: client.getClient(),
			body: { file: new File(['def run(value: str) -> dict:\n    return {"echo": value}\n'], 'echo.py', { type: 'text/x-python' }) },
			throwOnError: true,
		});
		fn = client.NotteFunction({ function_id: created.data.function_id });
	}, 60000);

	afterAll(async () => {
		if (fn) await functionDelete({ client: client.getClient(), path: { function_id: fn.functionId }, throwOnError: true });
	}, 60000);

	it.each([true, false])('executes and retrieves a pre-created run (stream=%s)', { timeout: 120000 }, async stream => {
		const functionObject = fn!;
		const created = await functionObject.createRun();
		expect(created.function_id).toBe(functionObject.functionId);
		expect(created.function_run_id).toBeTruthy();
		try {
			const before = await functionObject.getRun(created.function_run_id);
			expect(before.result).toBeNull();
			expect(before.local).toBe(false);
			const variables = { value: `node-sdk-${stream}-${Date.now()}` };
			const result = await functionObject.run(variables, { functionRunId: created.function_run_id, stream });
			expect(result.function_run_id).toBe(created.function_run_id);
			expect(result.status).toBe('closed');
			expect(result.result).toEqual({ echo: variables.value });
			const persisted = await functionObject.getRun(created.function_run_id);
			expect(persisted.status).toBe('closed');
			expect(persisted.variables).toEqual(variables);
			expect(JSON.parse(persisted.result!)).toEqual({ echo: variables.value });
			expect(await functionObject.retrieve(created.function_run_id)).toEqual(persisted);
		} finally {
			if ((await functionObject.getRun(created.function_run_id)).status === 'active') {
				await functionRunStop({ client: client.getClient(), path: { function_id: functionObject.functionId, run_id: created.function_run_id }, throwOnError: true });
			}
		}
	});
});
