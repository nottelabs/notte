import { writeFile } from 'node:fs/promises';
import { NotteClient } from '@/client';
import { Encryption } from '@/encryption';
import type {
	GetFunctionRunResponse,
	RunFunctionRequest,
	ListFunctionRunsByFunctionIdData,
	PaginatedResponseFunctionRunListItemResponse,
} from '@/lib/client/types.gen';
import {
	functionDownloadUrl,
	functionRunStart,
	functionRunGetMetadata,
	listFunctionRunsByFunctionId,
} from '@/lib/client/sdk.gen';
import { formatError } from '@/utils';
import { SDK_VERSION } from '@/version';

const DOWNLOAD_TIMEOUT_MS = 30_000;

/** Select extended for longer cloud execution. Defaults to standard (Lambda). */
export type FunctionRunOptions = Pick<RunFunctionRequest, 'runtime' | 'stream'> & {
	/** Stream logs and wait for completion. Defaults to true. */
	stream?: boolean;
	/** Receive streamed logs instead of printing them to console.log. */
	onLog?: (message: string) => void;
	/** Throw when execution fails. Defaults to true, matching Python. */
	raiseOnFailure?: boolean;
	/** Execute a record returned by createRun(). Omit to create a new run. */
	functionRunId?: GetFunctionRunResponse['function_run_id'];
};

/** Run record identifiers and creation time, before execution begins. */
export type FunctionRunCreateResult = Pick<GetFunctionRunResponse,
	'function_id' | 'function_run_id' | 'created_at'
>;

// The start endpoint is currently untyped in OpenAPI. Reuse the generated run
// metadata fields; the execution result is structured JSON, unlike the serialized
// string returned by retrieve(). Keep it unknown until the caller narrows it.
export type FunctionRunResult = Pick<GetFunctionRunResponse,
	'function_id' | 'function_run_id' | 'status' | 'session_id'
> & {
	result: unknown;
};

export type FunctionRunStartResult = Pick<GetFunctionRunResponse, 'function_run_id'> & {
	[key: string]: unknown;
};

export interface FunctionConstructor {
	function_id: string;
	decryption_key?: string;
}

export interface FunctionUrlOptions {
	/** Version to download. Defaults to the latest version. */
	version?: string;
	/** Overrides the decryption key passed to the constructor. */
	decryption_key?: string;
}

export interface FunctionDownloadOptions extends FunctionUrlOptions {
	/** Where to write the code. Must end with `.py`. Returned only when omitted. */
	path?: string;
}

/**
 * Query options for listing a function's runs: `page`, `page_size`,
 * `only_active`, `only_current_token`, `include_system`.
 */
export type FunctionRunListOptions = NonNullable<ListFunctionRunsByFunctionIdData['query']>;

/**
 * Function class for managing function runs
 */
export class NotteFunction {
	private client: NotteClient;
	public readonly functionId: string;
	public readonly decryptionKey?: string;

	constructor(client: NotteClient, options: FunctionConstructor) {
		this.client = client;
		this.functionId = options.function_id;
		this.decryptionKey = options.decryption_key;
	}

	/**
	 * Get metadata for a specific function run
	 */
	async getRun(functionRunId: string): Promise<GetFunctionRunResponse> {
		try {
			const response = await functionRunGetMetadata({
				client: this.client.getClient(),
				path: {
					function_id: this.functionId,
					run_id: functionRunId,
				},
			});

			if (response?.error) {
				throw new Error(`Failed to get function run metadata: ${formatError(response.error)}`);
			}

			return response.data;
		} catch (error) {
			if (error instanceof Error && error.message.startsWith('Failed to get function run metadata:')) {
				throw error;
			}
			throw new Error(`Failed to get function run metadata: ${error instanceof Error ? error.message : String(error)}`);
		}
	}

	/** Compatibility alias for getRun(). */
	async retrieve(functionRunId: string): Promise<GetFunctionRunResponse> {
		return this.getRun(functionRunId);
	}

	/**
	 * Create a cloud run record without starting execution.
	 * Optional: use this only when you need the ID before execution, then pass
	 * it to run(variables, { functionRunId }). run() otherwise creates a new run.
	 */
	async createRun(): Promise<FunctionRunCreateResult> {
		try {
			// These Python SDK endpoints are excluded from OpenAPI, so call them
			// through the generated HTTP client using generated metadata fields.
			const response = await this.client.getClient().post<{ 200: FunctionRunCreateResult }, unknown, true>({
				url: '/functions/{function_id}/runs/create',
				path: { function_id: this.functionId },
				body: { local: false } satisfies Pick<GetFunctionRunResponse, 'local'>,
				headers: { 'Content-Type': 'application/json' },
				parseAs: 'json',
				throwOnError: true,
			});
			return response.data;
		} catch (error) {
			throw new Error(`Failed to create function run: ${formatError(error)}`);
		}
	}

	/**
	 * List the runs of this function.
	 *
	 * `only_active` is sent as `false` unless the caller says otherwise, and that
	 * is deliberate rather than redundant. `GET /functions/{function_id}/runs`
	 * now defaults it to `false` server-side as well, but it used to default to
	 * `true`: the request model was a bare subclass of the session one, where
	 * "only active" reads sensibly as "list my running sessions" and, for "list
	 * this function's runs", was a trap. Hitting the endpoint with no query
	 * parameters returned only the runs executing right now - an empty list for
	 * any function that had finished. That cost us a bug in the anything-api
	 * console, where a function with 15 recorded runs displayed "Nothing has run
	 * this endpoint yet".
	 *
	 * Sending it explicitly pins this method to the documented behaviour against
	 * whichever API version it is talking to, including deployments that predate
	 * the server-side change. Callers who want only in-flight runs pass
	 * `only_active: true`.
	 */
	async runs(options: FunctionRunListOptions = {}): Promise<PaginatedResponseFunctionRunListItemResponse> {
		try {
			const response = await listFunctionRunsByFunctionId({
				client: this.client.getClient(),
				path: {
					function_id: this.functionId,
				},
				query: {
					...options,
					only_active: options.only_active ?? false,
				},
			});

			if (response?.error) {
				throw new Error(`Failed to list function runs: ${formatError(response.error)}`);
			}

			return response.data;
		} catch (error) {
			if (error instanceof Error && error.message.startsWith('Failed to list function runs:')) {
				throw error;
			}
			throw new Error(`Failed to list function runs: ${error instanceof Error ? error.message : String(error)}`);
		}
	}

	/**
	 * Stream logs and wait for the final result by default.
	 * Pass { stream: false } to receive the backend's JSON response without live logs.
	 * Disabling streaming does not make standard-runtime execution non-blocking.
	 * Pass functionRunId to execute a record returned by createRun().
	 */
	async run(variables: Record<string, unknown>, options: FunctionRunOptions & { stream: false }): Promise<FunctionRunStartResult>;
	async run(variables?: Record<string, unknown>, options?: FunctionRunOptions & { stream?: true }): Promise<FunctionRunResult>;
	async run(variables: Record<string, unknown>, options: FunctionRunOptions): Promise<FunctionRunStartResult | FunctionRunResult>;
	async run(variables: Record<string, unknown> = {}, options: FunctionRunOptions = {}): Promise<FunctionRunStartResult> {
		const apiKey = this.client.getConfig().apiKey || '';
		if (!apiKey) {
			throw new Error('API key is required. Provide it via config.apiKey or set the NOTTE_API_KEY environment variable.');
		}

		const stream = options.stream ?? true;
		try {
			const request = {
				parseAs: stream ? 'stream' as const : 'json' as const,
				path: {
					function_id: this.functionId,
				},
				headers: {
					'x-notte-api-key': apiKey,
					'x-notte-request-origin': 'sdk-node',
					'x-notte-sdk-version': SDK_VERSION,
				},
				body: {
					workflow_id: this.functionId,
					variables: variables,
					stream,
					...(options.runtime ? { runtime: options.runtime } : {}),
				},
			};
			const response = options.functionRunId === undefined
				? await functionRunStart({ ...request, client: this.client.getClient() })
				: await this.client.getClient().post({
					...request,
					url: '/functions/{function_id}/runs/{run_id}',
					path: { ...request.path, run_id: options.functionRunId },
					body: { ...request.body, function_run_id: options.functionRunId },
					headers: { ...request.headers, 'Content-Type': 'application/json' },
				});

			if (response?.error) {
				throw new Error(`Failed to start function run: ${formatError(response.error)}`);
			}

			const result = stream ? await readFunctionStream(
				response.data as unknown as ReadableStream<Uint8Array>,
				options.onLog ?? console.log,
			) : response.data as FunctionRunStartResult;
			if (result.status === 'failed' && (options.raiseOnFailure ?? true)) {
				throw new Error(`Function run ${result.function_run_id} failed: ${formatError(result.result)}`);
			}
			return result;
		} catch (error) {
			if (error instanceof Error && error.message.startsWith('Failed to start function run:')) {
				throw error;
			}
			throw new Error(`Failed to run function: ${error instanceof Error ? error.message : String(error)}`);
		}
	}

	/**
	 * Get the download URL of the function code, decrypting it when the API
	 * returns an encrypted one (Notte managed functions).
	 */
	async getUrl(options: FunctionUrlOptions = {}): Promise<string> {
		let response;
		try {
			response = await functionDownloadUrl({
				client: this.client.getClient(),
				path: {
					function_id: this.functionId,
				},
				query: options.version ? { version: options.version } : {},
			});
		} catch (error) {
			throw new Error(`Failed to get function download url: ${error instanceof Error ? error.message : String(error)}`);
		}

		if (response?.error) {
			throw new Error(`Failed to get function download url: ${formatError(response.error)}`);
		}

		const url = response.data.url;
		if (isHttpUrl(url)) {
			return url;
		}

		const decryptionKey = options.decryption_key ?? this.decryptionKey;
		if (!decryptionKey) {
			throw new Error(
				"Decryption key is required to decrypt the function download url. Set it when creating the function, i.e. client.NotteFunction({ function_id: '<your-function-id>', decryption_key: '<your-key>' })."
			);
		}

		let decrypted: string;
		try {
			decrypted = new Encryption(decryptionKey).decrypt(url);
		} catch (error) {
			throw new Error(`Failed to decrypt the function download url: ${error instanceof Error ? error.message : String(error)}. Contact support@notte.cc if you need help.`);
		}

		if (!isHttpUrl(decrypted)) {
			throw new Error('Failed to decrypt the function download url: the decrypted value is not a URL. Contact support@notte.cc if you need help.');
		}

		return decrypted;
	}

	/**
	 * Download the function code as a python file. Returns the code, and writes
	 * it to `path` when one is provided.
	 */
	async download(options: FunctionDownloadOptions = {}): Promise<string> {
		const { path } = options;
		if (path !== undefined && !path.endsWith('.py')) {
			throw new Error(`Code file path must end with .py, got '${path}'`);
		}

		const url = await this.getUrl(options);

		let response: Response;
		try {
			response = await fetch(url, { signal: AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS) });
		} catch (error) {
			// The url is presigned, so it is deliberately kept out of the message.
			throw new Error(`Failed to download function code: ${error instanceof Error ? error.message : String(error)}`);
		}

		if (!response.ok) {
			throw new Error(`Failed to download function code: ${response.status} ${response.statusText}`);
		}

		const code = await response.text();
		if (path !== undefined) {
			await writeFile(path, code, 'utf8');
		}

		return code;
	}

	/**
	 * Get the function ID
	 */
	getFunctionId(): string {
		return this.functionId;
	}
}

function isHttpUrl(value: string): boolean {
	return value.startsWith('https://') || value.startsWith('http://');
}

/** Consume SSE frames, including frames split across network/UTF-8 boundaries. */
async function readFunctionStream(body: ReadableStream<Uint8Array>, onLog: (message: string) => void): Promise<FunctionRunResult> {
	if (!body?.getReader) throw new Error('Missing function response stream');
	const reader = body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	let data: string[] = [];
	let result: FunctionRunResult | undefined;
	const dispatch = () => {
		if (!data.length) return;
		const event = JSON.parse(data.join('\n'));
		data = [];
		if (event.type === 'log') onLog(event.message);
		if (event.type === 'error') throw new Error(`Function stream error: ${event.message}`);
		if (event.type === 'result') {
			const value = typeof event.message === 'string' ? JSON.parse(event.message) : event.message;
			if (!value || typeof value.function_run_id !== 'string' || typeof value.function_id !== 'string'
				|| !['active', 'closed', 'failed'].includes(value.status) || !('result' in value)) {
				throw new Error('Invalid function result event');
			}
			result = value;
		}
	};
	const line = (value: string) => {
		if (value === '') dispatch();
		else if (value.startsWith('data:')) data.push(value.slice(5).replace(/^ /, ''));
	};
	try {
		while (true) {
			const { value, done } = await reader.read();
			buffer += decoder.decode(value, { stream: !done });
			let end: number;
			while ((end = buffer.indexOf('\n')) !== -1) {
				line(buffer.slice(0, end).replace(/\r$/, ''));
				buffer = buffer.slice(end + 1);
			}
			if (done) break;
		}
		if (buffer) line(buffer.replace(/\r$/, ''));
		dispatch();
		if (!result) throw new Error('Function stream ended without a result');
		return result;
	} finally {
		await reader.cancel().catch(() => {});
		reader.releaseLock();
	}
}
