import { describe, it, expect, beforeEach } from 'vitest';
import { readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { NotteClient } from '@/client';
import type { FunctionRunStartResult } from '@/functions';
import { config } from 'dotenv';
config();

describe.skipIf(!process.env.NOTTE_FUNCTION_ID)('Function Integration Tests', () => {
	let client: NotteClient;

	beforeEach(async () => {
		// Initialize client with API key from environment
		const apiKey = process.env.NOTTE_API_KEY;
		if (!apiKey) {
			throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
		}

		client = new NotteClient({
			apiKey,
			baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc'
		});
	});

	describe('Function Creation', () => {
		it('should create function instance with function_id', () => {
			const functionId = process.env.NOTTE_FUNCTION_ID!;
			const fn = client.NotteFunction({
				function_id: functionId
			});

			expect(fn).toBeDefined();
			expect(fn.getFunctionId()).toBe(functionId);
			expect(fn.functionId).toBe(functionId);
		});

		it('should create function instance with function_id and decryption_key', () => {
			const functionId = process.env.NOTTE_FUNCTION_ID!;
			const decryptionKey = process.env.NOTTE_FUNCTION_DECRYPTION_KEY || 'test-decryption-key'; // pragma: allowlist secret
			const fn = client.NotteFunction({
				function_id: functionId,
				decryption_key: decryptionKey
			});

			expect(fn).toBeDefined();
			expect(fn.getFunctionId()).toBe(functionId);
			expect(fn.functionId).toBe(functionId);
			expect(fn.decryptionKey).toBe(decryptionKey);
		});
	});

	describe('Function Run', () => {
		it('should run a function', { timeout: 300000 }, async () => {
			const functionId = process.env.NOTTE_FUNCTION_ID!;
			const fn = client.NotteFunction({
				function_id: functionId
			});

			const result = await fn.run({ url: 'https://example.com' });

			expect(result).toBeDefined();
			expect(result.function_run_id).toBeDefined();
			expect(typeof result.function_run_id).toBe('string');
			expect(result.status).toBe('closed');
			expect(result).toHaveProperty('result');
		});
	});

	describe('Function Metadata', () => {
		it('should get metadata for a function run', { timeout: 300000 }, async () => {
			const functionId = process.env.NOTTE_FUNCTION_ID!;
			const fn = client.NotteFunction({
				function_id: functionId
			});

			// First, start a function run
			const runResult = await fn.run({ url: 'https://example.com' }, { stream: false });

			expect(runResult).toBeDefined();
			const runId = runResult.function_run_id;
			expect(runId).toBeDefined();

			// Wait a bit for the run to be processed
			await new Promise(resolve => setTimeout(resolve, 2000));

			// Get metadata for the function run
			const metadata = await fn.retrieve(runId!);

			expect(metadata).toBeDefined();
			expect(metadata.function_run_id).toBe(runId);
		});
	});

	describe('Function Download', () => {
		it('should get a download url', { timeout: 60000 }, async () => {
			const functionId = process.env.NOTTE_FUNCTION_ID!;
			const fn = client.NotteFunction({
				function_id: functionId,
				decryption_key: process.env.NOTTE_FUNCTION_DECRYPTION_KEY
			});

			const url = await fn.getUrl();

			expect(url).toMatch(/^https?:\/\//);
		});

		it('should download the function code', { timeout: 60000 }, async () => {
			const functionId = process.env.NOTTE_FUNCTION_ID!;
			const fn = client.NotteFunction({
				function_id: functionId,
				decryption_key: process.env.NOTTE_FUNCTION_DECRYPTION_KEY
			});

			const code = await fn.download();

			expect(code).toContain('def run(');
		});

		it('should download the function code to a file', { timeout: 60000 }, async () => {
			const functionId = process.env.NOTTE_FUNCTION_ID!;
			const fn = client.NotteFunction({
				function_id: functionId,
				decryption_key: process.env.NOTTE_FUNCTION_DECRYPTION_KEY
			});
			const target = join(tmpdir(), `notte-function-${Date.now()}.py`);

			try {
				const code = await fn.download({ path: target });

				expect(readFileSync(target, 'utf8')).toBe(code);
			} finally {
				rmSync(target, { force: true });
			}
		});

		it('should reject a path that is not a python file', async () => {
			const fn = client.NotteFunction({
				function_id: process.env.NOTTE_FUNCTION_ID!
			});

			await expect(fn.download({ path: 'invalid_file.txt' })).rejects.toThrow(
				'Code file path must end with .py'
			);
		});
	});

	describe('Function Properties', () => {
		it('should expose functionId property', () => {
			const functionId = process.env.NOTTE_FUNCTION_ID!;
			const fn = client.NotteFunction({
				function_id: functionId
			});

			expect(fn.functionId).toBe(functionId);
			expect(fn.getFunctionId()).toBe(functionId);
		});

		it('should expose decryptionKey property when provided', () => {
			const functionId = process.env.NOTTE_FUNCTION_ID!;
			const decryptionKey = process.env.NOTTE_FUNCTION_DECRYPTION_KEY || 'test-decryption-key'; // pragma: allowlist secret
			const fn = client.NotteFunction({
				function_id: functionId,
				decryption_key: decryptionKey
			});

			expect(fn.decryptionKey).toBe(decryptionKey);
		});
	});

});
