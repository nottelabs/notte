import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { NotteClient } from '../src/client';
import { NotteFunction } from '../src/functions';

// Mock the service functions
vi.mock('@/lib/client/sdk.gen', () => ({
	functionRunGetMetadata: vi.fn(),
	functionRunStart: vi.fn(),
	functionDownloadUrl: vi.fn(),
	listFunctionRunsByFunctionId: vi.fn(),
}));

vi.mock('../src/version', () => ({
	SDK_VERSION: '1.0.0',
}));

import { functionRunGetMetadata, functionRunStart, functionDownloadUrl, listFunctionRunsByFunctionId } from '@/lib/client/sdk.gen';

// Mock the client
const mockClient = {
	getClient: vi.fn(() => ({
		// Mock client methods
	})),
	getConfig: vi.fn(() => ({
		apiKey: 'test-api-key', // pragma: allowlist secret
		baseUrl: 'https://api.notte.cc',
	})),
} as unknown as NotteClient;

// Produced by the python SDK: Encryption(root_key=DECRYPTION_KEY).encrypt(DECRYPTED_URL)
const DECRYPTION_KEY = 'public-sdk-test-key'; // pragma: allowlist secret
const DECRYPTED_URL = 'https://example.com/function.py?signature=test';
const ENCRYPTED_URL =
	'qWKF5mcl2_w6hv6qHgdIi2dBQUFBQUJxbzlpRElXZlhzUHYzNEV3SGVqSDQ1MjRVMkNUcGx6Z3ZnMDlLdmhMWEx6YXY5Sk0zTzZIMWgxT0tUYmhfM0JRWW9RbE1uYUlOOEhRc0FiTXBvWXRraTZkUmd6WHR1eXcwbERnR3o0UDI3X2xlSWRFa1l5bUtsSW4yOGdrdkk0dE9BZXRU'; // pragma: allowlist secret
const PLAIN_URL = 'https://files.us-script.notte.cc/tenant/function/v1.py?signature=plain';

function mockDownloadUrl(url: string) {
	vi.mocked(functionDownloadUrl).mockResolvedValue({
		data: { url },
		error: undefined,
	} as any);
}

function mockRunList() {
	const page = { items: [], page: 1, page_size: 10, has_next: false, has_previous: false };
	vi.mocked(listFunctionRunsByFunctionId).mockResolvedValue({
		data: page,
		error: undefined,
	} as any);
	return page;
}

function queryOf(mock: typeof listFunctionRunsByFunctionId) {
	return vi.mocked(mock).mock.calls[0][0].query;
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

describe('NotteFunction', () => {
	let fn: NotteFunction;

	beforeEach(() => {
		vi.clearAllMocks();
		fn = new NotteFunction(mockClient, {
			function_id: '9fb6d40e-c76a-4d44-a73a-aa7843f0f535',
			decryption_key: 'public-sdk-test-key' // pragma: allowlist secret
		});
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('should create a function instance with correct function ID', () => {
		expect(fn.getFunctionId()).toBe('9fb6d40e-c76a-4d44-a73a-aa7843f0f535');
	});

	it('should have the correct function ID property', () => {
		expect(fn.functionId).toBe('9fb6d40e-c76a-4d44-a73a-aa7843f0f535');
	});

	it('should have the correct decryption key property', () => {
		expect(fn.decryptionKey).toBe('public-sdk-test-key'); // pragma: allowlist secret
	});

	it('should create function with required constructor parameters', () => {
		const testFn = new NotteFunction(mockClient, {
			function_id: 'another-function-id',
			decryption_key: 'another-decryption-key'
		});
		expect(testFn.getFunctionId()).toBe('another-function-id');
		expect(testFn.decryptionKey).toBe('another-decryption-key');
	});

	it('should create function without decryption key', () => {
		const testFn = new NotteFunction(mockClient, {
			function_id: 'function-without-key'
		});
		expect(testFn.getFunctionId()).toBe('function-without-key');
		expect(testFn.decryptionKey).toBeUndefined();
	});

	describe('retrieve', () => {
		it('should successfully retrieve function run metadata', async () => {
			const mockResponse = {
				data: {
					function_id: '9fb6d40e-c76a-4d44-a73a-aa7843f0f535',
					function_run_id: 'test-run-id',
					created_at: '2023-01-01T00:00:00Z',
					updated_at: '2023-01-01T00:00:00Z',
					status: 'active' as const,
				},
				error: undefined,
				request: {} as Request,
				response: {} as Response,
			};

			vi.mocked(functionRunGetMetadata).mockResolvedValue(mockResponse as any);

			const result = await fn.retrieve('test-run-id');

			expect(functionRunGetMetadata).toHaveBeenCalledWith({
				client: mockClient.getClient(),
				path: {
					function_id: '9fb6d40e-c76a-4d44-a73a-aa7843f0f535',
					run_id: 'test-run-id',
				},
			});

			expect(result).toEqual(mockResponse.data);
		});

		it('should throw error when retrieve fails with API error', async () => {
			const mockResponse = {
				data: undefined,
				error: { message: 'API Error' } as any,
				request: {} as Request,
				response: {} as Response,
			};

			vi.mocked(functionRunGetMetadata).mockResolvedValue(mockResponse as any);

			await expect(fn.retrieve('test-run-id')).rejects.toThrow(
				'Failed to get function run metadata: API Error'
			);
		});

		it('should throw error when retrieve fails with exception', async () => {
			vi.mocked(functionRunGetMetadata).mockRejectedValue(new Error('Network error'));

			await expect(fn.retrieve('test-run-id')).rejects.toThrow(
				'Failed to get function run metadata: Network error'
			);
		});
	});

	describe('run', () => {
		it('should return the JSON response when streaming is disabled', async () => {
			const mockResponse = {
				data: 'function-run-response',
				error: undefined,
				request: {} as Request,
				response: {} as Response,
			};

			vi.mocked(functionRunStart).mockResolvedValue(mockResponse as any);

			const result = await fn.run({ "test": "test" }, { stream: false });

			expect(functionRunStart).toHaveBeenCalledWith({
				parseAs: 'json',
				client: mockClient.getClient(),
				path: {
					function_id: '9fb6d40e-c76a-4d44-a73a-aa7843f0f535',
				},
				headers: {
					'x-notte-api-key': 'test-api-key',
					'x-notte-request-origin': 'sdk-node',
					'x-notte-sdk-version': '1.0.0',
				},
				body: {
					workflow_id: '9fb6d40e-c76a-4d44-a73a-aa7843f0f535',
					variables: { "test": "test"},
					stream: false,
				},
			});

			expect(result).toBe('function-run-response');
		});

		it('keeps runtime selection separate from script variables', async () => {
			vi.mocked(functionRunStart).mockResolvedValue({ data: { function_run_id: 'test' } } as any);
			await fn.run({ runtime: 'script-input', wait_seconds: 960 }, { runtime: 'extended', stream: false });
			expect(vi.mocked(functionRunStart).mock.calls[0][0].body).toEqual({
				workflow_id: fn.functionId,
				variables: { runtime: 'script-input', wait_seconds: 960 },
				stream: false,
				runtime: 'extended',
			});
		});

		it('should throw error when run fails with API error', async () => {
			const mockResponse = {
				data: undefined,
				error: { message: 'Function not found' } as any,
				request: {} as Request,
				response: {} as Response,
			};

			vi.mocked(functionRunStart).mockResolvedValue(mockResponse as any);

			await expect(fn.run()).rejects.toThrow(
				'Failed to start function run: Function not found'
			);
		});

		it('should throw error when run fails with exception', async () => {
			vi.mocked(functionRunStart).mockRejectedValue(new Error('Connection timeout'));

			await expect(fn.run()).rejects.toThrow(
				'Failed to run function: Connection timeout'
			);
		});
	});

	describe('getUrl', () => {
		it('should read the url field of the response', async () => {
			mockDownloadUrl(PLAIN_URL);

			await expect(fn.getUrl()).resolves.toBe(PLAIN_URL);

			expect(functionDownloadUrl).toHaveBeenCalledWith({
				client: mockClient.getClient(),
				path: {
					function_id: '9fb6d40e-c76a-4d44-a73a-aa7843f0f535',
				},
				query: {},
			});
		});

		it('should forward the requested version', async () => {
			mockDownloadUrl(PLAIN_URL);

			await fn.getUrl({ version: 'v1.0.0' });

			expect(functionDownloadUrl).toHaveBeenCalledWith(
				expect.objectContaining({ query: { version: 'v1.0.0' } })
			);
		});

		it('should decrypt an encrypted url with the constructor key', async () => {
			mockDownloadUrl(ENCRYPTED_URL);

			await expect(fn.getUrl()).resolves.toBe(DECRYPTED_URL);
		});

		it('should decrypt an encrypted url with a per-call key', async () => {
			mockDownloadUrl(ENCRYPTED_URL);
			const keyless = new NotteFunction(mockClient, { function_id: 'fn-id' });

			await expect(keyless.getUrl({ decryption_key: DECRYPTION_KEY })).resolves.toBe(DECRYPTED_URL);
		});

		it('should throw when an encrypted url has no decryption key', async () => {
			mockDownloadUrl(ENCRYPTED_URL);
			const keyless = new NotteFunction(mockClient, { function_id: 'fn-id' });

			await expect(keyless.getUrl()).rejects.toThrow('Decryption key is required');
		});

		it('should throw when the decryption key is wrong', async () => {
			mockDownloadUrl(ENCRYPTED_URL);

			await expect(fn.getUrl({ decryption_key: 'wrong-key' })).rejects.toThrow(
				'Failed to decrypt the function download url'
			);
		});

		it('should throw error when the API returns an error', async () => {
			vi.mocked(functionDownloadUrl).mockResolvedValue({
				data: undefined,
				error: { message: 'Function not found' },
			} as any);

			await expect(fn.getUrl()).rejects.toThrow(
				'Failed to get function download url: Function not found'
			);
		});

		it('should throw error when the request fails', async () => {
			vi.mocked(functionDownloadUrl).mockRejectedValue(new Error('Connection timeout'));

			await expect(fn.getUrl()).rejects.toThrow(
				'Failed to get function download url: Connection timeout'
			);
		});
	});

	describe('download', () => {
		const CODE = 'def run(url: str):\n    return url\n';

		it('should return the downloaded code', async () => {
			mockDownloadUrl(PLAIN_URL);
			const fetchMock = mockFetch({ ok: true, text: CODE });

			await expect(fn.download()).resolves.toBe(CODE);
			expect(fetchMock).toHaveBeenCalledWith(PLAIN_URL, expect.anything());
		});

		it('should write the code to the given path', async () => {
			mockDownloadUrl(PLAIN_URL);
			mockFetch({ ok: true, text: CODE });
			const target = join(tmpdir(), `notte-download-${Date.now()}.py`);

			try {
				await expect(fn.download({ path: target })).resolves.toBe(CODE);
				expect(readFileSync(target, 'utf8')).toBe(CODE);
			} finally {
				rmSync(target, { force: true });
			}
		});

		it('should reject a path that is not a python file', async () => {
			mockDownloadUrl(PLAIN_URL);

			await expect(fn.download({ path: 'invalid_file.txt' })).rejects.toThrow(
				"Code file path must end with .py, got 'invalid_file.txt'"
			);
			expect(functionDownloadUrl).not.toHaveBeenCalled();
		});

		it('should throw when the file server returns an error status', async () => {
			mockDownloadUrl(PLAIN_URL);
			mockFetch({ ok: false, status: 403, statusText: 'Forbidden' });

			await expect(fn.download()).rejects.toThrow('Failed to download function code: 403 Forbidden');
		});

		it('should not leak the presigned url when the download fails', async () => {
			mockDownloadUrl(PLAIN_URL);
			vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('socket hang up')));

			await expect(fn.download()).rejects.toThrow('Failed to download function code: socket hang up');
			await expect(fn.download()).rejects.not.toThrow(PLAIN_URL);
		});
	});

	describe('runs', () => {
		// This method sends only_active=false explicitly instead of relying on the
		// endpoint default, so a finished function is never answered with an empty
		// list - including on API versions that predate the server-side default
		// flipping to false. Keep these two assertions.
		it('should ask for every run, not just the active ones, by default', async () => {
			mockRunList();

			await fn.runs();

			expect(queryOf(listFunctionRunsByFunctionId)).toEqual({ only_active: false });
		});

		it('should let the caller opt back in to active-only runs', async () => {
			mockRunList();

			await fn.runs({ only_active: true });

			expect(queryOf(listFunctionRunsByFunctionId)).toEqual({ only_active: true });
		});

		it('should return the paginated response and target the function', async () => {
			const page = mockRunList();

			await expect(fn.runs()).resolves.toEqual(page);

			expect(listFunctionRunsByFunctionId).toHaveBeenCalledWith(
				expect.objectContaining({
					client: mockClient.getClient(),
					path: { function_id: '9fb6d40e-c76a-4d44-a73a-aa7843f0f535' },
				})
			);
		});

		it('should forward pagination and filter options', async () => {
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

		it('should keep the false default when only_active is passed as undefined', async () => {
			mockRunList();

			await fn.runs({ only_active: undefined });

			expect(queryOf(listFunctionRunsByFunctionId)).toEqual({ only_active: false });
		});

		it('should throw error when the API returns an error', async () => {
			vi.mocked(listFunctionRunsByFunctionId).mockResolvedValue({
				data: undefined,
				error: { message: 'Function not found' },
			} as any);

			await expect(fn.runs()).rejects.toThrow('Failed to list function runs: Function not found');
		});

		it('should throw error when the request fails', async () => {
			vi.mocked(listFunctionRunsByFunctionId).mockRejectedValue(new Error('Connection timeout'));

			await expect(fn.runs()).rejects.toThrow('Failed to list function runs: Connection timeout');
		});
	});
});
