import { readFile, writeFile } from 'node:fs/promises';
import { basename } from 'node:path';
import { NotteClient, TIMEOUT_HEADER } from '@/client';
import { Encryption } from '@/encryption';
import { FailedToRunCloudFunctionError, InvalidRequestError, NotteAPIError, NotteError, NotteTimeoutError } from '@/errors';
import type {
	DeleteFunctionResponse,
	FunctionMetadataUpdateRequest,
	FunctionResponse,
	FunctionRollbackRequest,
	FunctionScheduleCreateRequest,
	FunctionWithLinkResponse,
	GetFunctionRunResponse,
	ListFunctionRunsByFunctionIdData,
	PaginatedResponseFunctionRunListItemResponse,
	RunFunctionRequest,
	ScheduleDeleteResponse,
	ScheduleResponse,
} from '@/lib/client/types.gen';
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

const DOWNLOAD_TIMEOUT_MS = 30_000;
/** Default deadline of `run()`, the counterpart of `WorkflowsClient.WORKFLOW_RUN_TIMEOUT` (5 minutes). */
export const FUNCTION_RUN_TIMEOUT_MS = 5 * 60 * 1000;

/**
 * Run endpoints that the OpenAPI spec does not describe. They are the Python
 * SDK's `WorkflowsClient.CREATE_WORKFLOW_RUN` and `START_WORKFLOW_RUN` paths
 * and are only ever called through `NotteFunction.postRunEndpoint()`.
 */
export const FUNCTION_RUN_ENDPOINTS = {
	/** `POST` creates a run record without executing it (`CreateFunctionRunRequest`). */
	create: '/functions/{function_id}/runs/create',
	/** `POST` executes a previously created run (`StartFunctionRunRequest`). */
	start: '/functions/{function_id}/runs/{run_id}',
} as const;

/**
 * The run endpoints hand the caller's key to the execution runtime through
 * this header (the `Authorization` header is not forwarded), so `run()` sends
 * it whenever the client holds a key, like `WorkflowsClient.run` in Python.
 * Proxy-mode clients have no key; their proxy must add the header itself.
 */
export const RUN_API_KEY_HEADER = 'x-notte-api-key'; // pragma: allowlist secret

export type FunctionRuntime = NonNullable<RunFunctionRequest['runtime']>;
export type FunctionRunStatus = GetFunctionRunResponse['status'];
const FUNCTION_RUNTIMES: readonly FunctionRuntime[] = ['standard', 'extended'];
const FUNCTION_RUN_STATUSES: readonly FunctionRunStatus[] = ['closed', 'active', 'failed'];

/** Reference an existing function by ID. */
export interface FunctionConstructorWithId {
	function_id: string;
	/** Key used to decrypt the download URL of Notte managed functions. */
	decryption_key?: string;
	path?: never;
}

/**
 * Create a function from a local `.py` file, like `client.Function(path=...)`
 * in Python. The upload happens on the first operation that needs the ID.
 */
export interface FunctionConstructorCreate {
	/** Path to the python file containing the `run` function. Must end with `.py`. */
	path: string;
	name?: string | null;
	description?: string | null;
	/** Whether the function is public and shared with other users. Defaults to false. */
	shared?: boolean;
	decryption_key?: string;
	function_id?: never;
}

export type FunctionConstructor = FunctionConstructorWithId | FunctionConstructorCreate;

/** Result of executing a run, the counterpart of `FunctionRunResponse` in Python. */
export interface FunctionRunResult {
	function_id: string;
	function_run_id: string;
	session_id: string | null;
	/** The value returned by the script's `run` function, decoded from JSON. */
	result: unknown;
	status: FunctionRunStatus;
}
/** Alias of `FunctionRunResult` using the Python model name. */
export type FunctionRunResponse = FunctionRunResult;
/** @deprecated `run()` now returns `FunctionRunResult` whether or not it streams. */
export type FunctionRunStartResult = FunctionRunResult;

/** Run record returned by `createRun()`, the counterpart of `CreateFunctionRunResponse` in Python. */
export interface FunctionRunCreateResult {
	function_id: string;
	function_run_id: string;
	created_at: string;
	status: 'created';
}

export interface FunctionRunCreateOptions {
	/** Mark the record as a local run. Defaults to false; the Node SDK only executes on the cloud. */
	local?: boolean;
}

export interface FunctionRunOptions {
	/** Stream logs and wait for completion. Defaults to true. */
	stream?: boolean;
	/** Receive streamed logs instead of printing them to console.log. */
	onLog?: (message: string) => void;
	/** Throw `FailedToRunCloudFunctionError` when execution fails. Defaults to true, matching Python. */
	raiseOnFailure?: boolean;
	/** Execute a record returned by createRun(). Omit to create a new run. */
	functionRunId?: string;
	/** Override the saved function runtime; omit to inherit its default. */
	runtime?: FunctionRuntime;
	/**
	 * Deadline of the whole execution in milliseconds. The wait is aborted with
	 * `NotteTimeoutError` once it elapses. Defaults to `FUNCTION_RUN_TIMEOUT_MS` (5 minutes).
	 */
	timeoutMs?: number;
}

export interface FunctionGetOptions {
	/** Version to fetch. Defaults to the latest version. */
	version?: string;
}

export interface FunctionUrlOptions extends FunctionGetOptions {
	/** Overrides the decryption key passed to the constructor. */
	decryption_key?: string;
}

export interface FunctionDownloadOptions extends FunctionUrlOptions {
	/** Where to write the code. Must end with `.py`. Returned only when omitted. */
	path?: string;
}

export interface FunctionUpdateOptions {
	/** Path to the new python code. Must end with `.py`. */
	path?: string;
	/** Only update this version. Defaults to creating a new version. */
	version?: string;
	/** Whether to restrict the function code. Defaults to true, like Python. */
	restricted?: boolean;
}

/** Metadata fields accepted by `PATCH /functions/{function_id}`. */
export type FunctionMetadataUpdateOptions = FunctionMetadataUpdateRequest;

export interface FunctionScheduleOptions {
	/** Cron expression of the schedule. */
	cron: FunctionScheduleCreateRequest['cron'];
	/** Variables passed to every scheduled run. */
	variables?: FunctionScheduleCreateRequest['variables'];
}

export interface FunctionRollbackOptions extends FunctionRollbackRequest {
	/** Whether to restrict the function code. Defaults to true, like `update()`. */
	restricted?: boolean;
}

/**
 * Query options for listing a function's runs: `page`, `page_size`,
 * `only_active`, `only_current_token`, `include_system`, `source`.
 */
export type FunctionRunListOptions = NonNullable<ListFunctionRunsByFunctionIdData['query']>;

type FunctionRunEndpointRequest = {
	url: (typeof FUNCTION_RUN_ENDPOINTS)[keyof typeof FUNCTION_RUN_ENDPOINTS];
	path: { function_id: string; run_id?: string };
	body: Record<string, unknown>;
	parseAs?: 'json' | 'stream';
	headers?: Record<string, string>;
	signal?: AbortSignal;
};

/**
 * Cloud function saved in the Notte console, the counterpart of
 * `notte.Function` in Python.
 *
 * ```ts
 * const fn = client.NotteFunction({ function_id: '<your-function-id>' });
 * const result = await fn.run({ url: 'https://example.com' });
 *
 * const created = client.NotteFunction({ path: './scraper.py', name: 'Scraper' });
 * await created.run(); // uploads scraper.py first
 * ```
 */
export class NotteFunction {
	private readonly client: NotteClient;
	private _functionId: string | null = null;
	private initPromise: Promise<string> | null = null;
	private createData: FunctionConstructorCreate | null = null;
	public readonly decryptionKey?: string;

	constructor(client: NotteClient, options: FunctionConstructor) {
		this.client = client;
		this.decryptionKey = options.decryption_key;
		if (options.function_id !== undefined) {
			if (options.function_id.length === 0) {
				throw new InvalidRequestError('function_id cannot be empty');
			}
			this._functionId = options.function_id;
		} else if (options.path !== undefined) {
			assertPythonPath(options.path);
			// Defer the upload until an operation needs the ID, like NotteVault.
			this.createData = options;
		} else {
			throw new InvalidRequestError("Either 'function_id' or 'path' must be provided");
		}
	}

	/** The function ID. Throws before a `path`-constructed function has been uploaded. */
	get functionId(): string {
		if (this._functionId === null) {
			throw new InvalidRequestError(
				'Function not initialized. Await a function operation (for example `await fn.get()`) before reading its ID.',
			);
		}
		return this._functionId;
	}

	/** Alias of the `functionId` accessor. */
	getFunctionId(): string {
		return this.functionId;
	}

	private async ensureInitialized(): Promise<string> {
		if (this._functionId !== null) {
			return this._functionId;
		}
		if (this.initPromise === null) {
			const createData = this.createData;
			this.createData = null;
			if (createData === null) {
				throw new InvalidRequestError('Function not initialized');
			}
			this.initPromise = this.createFunction(createData);
		}
		return this.initPromise;
	}

	private async createFunction(data: FunctionConstructorCreate): Promise<string> {
		const file = await readPythonFile(data.path);
		const response = await functionCreate({
			client: this.client.getClient(),
			throwOnError: true,
			body: { file, name: data.name, description: data.description, shared: data.shared },
		});
		this._functionId = response.data.function_id;
		console.info(`[Function] ${this._functionId} created successfully.`);
		return this._functionId;
	}

	/**
	 * Get the function metadata together with its download URL, the
	 * counterpart of `client.functions.get()` in Python.
	 *
	 * ```ts
	 * const { latest_version, versions } = await fn.get();
	 * ```
	 */
	async get(options: FunctionGetOptions = {}): Promise<FunctionWithLinkResponse> {
		const functionId = await this.ensureInitialized();
		const response = await functionDownloadUrl({
			client: this.client.getClient(),
			throwOnError: true,
			path: { function_id: functionId },
			query: options.version !== undefined ? { version: options.version } : {},
		});
		return response.data;
	}

	/**
	 * Upload a new version of the code, mirroring `function.update(path=...)`.
	 *
	 * ```ts
	 * const updated = await fn.update({ path: './scraper.py' });
	 * console.log(updated.latest_version);
	 * ```
	 */
	async update(options: FunctionUpdateOptions): Promise<FunctionResponse> {
		if (options.path === undefined) {
			throw new InvalidRequestError("'path' must be provided");
		}
		const functionId = await this.ensureInitialized();
		const file = await readPythonFile(options.path);
		const response = await functionUpdate({
			client: this.client.getClient(),
			throwOnError: true,
			path: { function_id: functionId },
			query: {
				restricted: options.restricted ?? true,
				...(options.version !== undefined ? { version: options.version } : {}),
			},
			body: { file },
		});
		console.info(`[Function] ${functionId} updated successfully to version ${response.data.latest_version}.`);
		return response.data;
	}

	/**
	 * Update the function metadata (name, description, default runtime, ...).
	 *
	 * ```ts
	 * await fn.updateMetadata({ name: 'Price monitor', default_runtime: 'extended' });
	 * ```
	 */
	async updateMetadata(options: FunctionMetadataUpdateOptions): Promise<FunctionResponse> {
		const functionId = await this.ensureInitialized();
		const response = await functionMetadataUpdate({
			client: this.client.getClient(),
			throwOnError: true,
			path: { function_id: functionId },
			body: options,
		});
		return response.data;
	}

	/**
	 * Delete the function from the Notte console.
	 *
	 * ```ts
	 * await fn.delete();
	 * ```
	 */
	async delete(): Promise<DeleteFunctionResponse> {
		const functionId = await this.ensureInitialized();
		const response = await functionDelete({
			client: this.client.getClient(),
			throwOnError: true,
			path: { function_id: functionId },
		});
		console.info(`[Function] ${functionId} deleted successfully.`);
		return response.data;
	}

	/**
	 * Schedule the function to run on a cron expression.
	 *
	 * ```ts
	 * await fn.setSchedule({ cron: '0 9 * * *', variables: { url: 'https://example.com' } });
	 * ```
	 */
	async setSchedule(options: FunctionScheduleOptions): Promise<ScheduleResponse> {
		const functionId = await this.ensureInitialized();
		const response = await functionScheduleSet({
			client: this.client.getClient(),
			throwOnError: true,
			path: { function_id: functionId },
			body: { cron: options.cron, variables: options.variables ?? null },
		});
		return response.data;
	}

	/**
	 * Remove the function schedule.
	 *
	 * ```ts
	 * await fn.deleteSchedule();
	 * ```
	 */
	async deleteSchedule(): Promise<ScheduleDeleteResponse> {
		const functionId = await this.ensureInitialized();
		const response = await functionScheduleDelete({
			client: this.client.getClient(),
			throwOnError: true,
			path: { function_id: functionId },
		});
		return response.data;
	}

	/**
	 * Roll the function back to a previous version.
	 *
	 * ```ts
	 * const { versions } = await fn.get();
	 * await fn.rollback({ version: versions[0] });
	 * ```
	 */
	async rollback(options: FunctionRollbackOptions): Promise<FunctionResponse> {
		const functionId = await this.ensureInitialized();
		const response = await functionRollback({
			client: this.client.getClient(),
			throwOnError: true,
			path: { function_id: functionId },
			query: { restricted: options.restricted ?? true },
			body: { version: options.version },
		});
		return response.data;
	}

	/**
	 * Get metadata for a specific function run.
	 *
	 * ```ts
	 * const run = await fn.getRun(result.function_run_id);
	 * console.log(run.status, run.logs);
	 * ```
	 */
	async getRun(functionRunId: string): Promise<GetFunctionRunResponse> {
		const functionId = await this.ensureInitialized();
		const response = await functionRunGetMetadata({
			client: this.client.getClient(),
			throwOnError: true,
			path: { function_id: functionId, run_id: functionRunId },
		});
		return response.data;
	}

	/**
	 * Compatibility alias for getRun().
	 * @deprecated Use getRun() instead. Retained for backwards compatibility.
	 */
	async retrieve(functionRunId: string): Promise<GetFunctionRunResponse> {
		return this.getRun(functionRunId);
	}

	/**
	 * Create a cloud run record without starting execution, like
	 * `function.create_run()` in Python. Use this only when you need the ID
	 * before execution, then pass it to `run(variables, { functionRunId })`.
	 * `run()` otherwise creates a new run on its own.
	 *
	 * ```ts
	 * const created = await fn.createRun();
	 * const result = await fn.run({ url: 'https://example.com' }, { functionRunId: created.function_run_id });
	 * ```
	 */
	async createRun(options: FunctionRunCreateOptions = {}): Promise<FunctionRunCreateResult> {
		const functionId = await this.ensureInitialized();
		return this.postRunEndpoint<FunctionRunCreateResult>({
			url: FUNCTION_RUN_ENDPOINTS.create,
			path: { function_id: functionId },
			body: { local: options.local ?? false },
		});
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
	 *
	 * ```ts
	 * const { items } = await fn.runs({ page_size: 20 });
	 * ```
	 */
	async runs(options: FunctionRunListOptions = {}): Promise<PaginatedResponseFunctionRunListItemResponse> {
		const functionId = await this.ensureInitialized();
		const response = await listFunctionRunsByFunctionId({
			client: this.client.getClient(),
			throwOnError: true,
			path: { function_id: functionId },
			query: { ...options, only_active: options.only_active ?? false },
		});
		return response.data;
	}

	/**
	 * Run the function on the cloud and wait for its result, streaming logs by
	 * default like `function.run(**variables)` in Python.
	 *
	 * Pass `{ stream: false }` to receive the backend's JSON response without
	 * live logs; execution still blocks until completion. Pass `functionRunId`
	 * to execute a record returned by `createRun()`; otherwise a new run record
	 * is created first, exactly like Python. A failed execution throws
	 * `FailedToRunCloudFunctionError` unless `raiseOnFailure` is false, and the
	 * wait is aborted with `NotteTimeoutError` after `timeoutMs`.
	 *
	 * ```ts
	 * const result = await fn.run({ url: 'https://example.com' });
	 * console.log(result.result);
	 *
	 * await fn.run({ url: 'https://example.com' }, { runtime: 'extended', onLog: line => logger.info(line) });
	 * ```
	 */
	async run(variables: Record<string, unknown> = {}, options: FunctionRunOptions = {}): Promise<FunctionRunResult> {
		const stream = options.stream ?? true;
		const timeoutMs = options.timeoutMs ?? FUNCTION_RUN_TIMEOUT_MS;
		if (!(timeoutMs > 0)) {
			throw new InvalidRequestError('timeoutMs must be a positive number');
		}
		if (options.runtime !== undefined && !FUNCTION_RUNTIMES.includes(options.runtime)) {
			throw new InvalidRequestError(`runtime must be one of ${FUNCTION_RUNTIMES.join(', ')}, got '${String(options.runtime)}'`);
		}
		const functionId = await this.ensureInitialized();
		// Create the run record first, like RemoteWorkflow.run in Python.
		const functionRunId = options.functionRunId ?? (await this.createRun()).function_run_id;
		const body: RunFunctionRequest = {
			workflow_id: functionId,
			variables,
			stream,
			...(options.runtime !== undefined ? { runtime: options.runtime } : {}),
		};
		// The run deadline replaces the client's per-request timeout, which would
		// otherwise cut a long execution (or its log stream) short.
		const headers: Record<string, string> = { [TIMEOUT_HEADER]: '0' };
		const apiKey = this.client.getConfig().apiKey;
		if (apiKey) {
			headers[RUN_API_KEY_HEADER] = apiKey;
		}
		const endpointPath = FUNCTION_RUN_ENDPOINTS.start
			.replace('{function_id}', functionId)
			.replace('{run_id}', functionRunId);
		const parseAs = stream ? 'stream' : 'json';
		const controller = new AbortController();
		let timedOut = false;
		const timer = Number.isFinite(timeoutMs)
			? setTimeout(() => {
				timedOut = true;
				controller.abort(new DOMException(`Function run timed out after ${timeoutMs}ms`, 'TimeoutError'));
			}, timeoutMs)
			: undefined;
		timer?.unref?.();
		try {
			const raw = await this.postRunEndpoint<unknown>({
				url: FUNCTION_RUN_ENDPOINTS.start,
				path: { function_id: functionId, run_id: functionRunId },
				body: { ...body, function_run_id: functionRunId },
				parseAs,
				headers,
				signal: controller.signal,
			});
			const result = stream
				? await readFunctionStream(raw as ReadableStream<Uint8Array>, options.onLog ?? console.log, endpointPath, controller.signal)
				: parseFunctionRunResult(raw, endpointPath);
			if (result.status === 'failed' && (options.raiseOnFailure ?? true)) {
				throw new FailedToRunCloudFunctionError(functionId, result.function_run_id, result);
			}
			return result;
		} catch (error) {
			if (timedOut) {
				throw new NotteTimeoutError(`Function ${functionId} run timed out after ${timeoutMs}ms`, { cause: error });
			}
			throw error;
		} finally {
			clearTimeout(timer);
		}
	}

	/**
	 * Get the download URL of the function code, decrypting it when the API
	 * returns an encrypted one (Notte managed functions).
	 *
	 * ```ts
	 * const url = await fn.getUrl({ version: 'v1' });
	 * ```
	 */
	async getUrl(options: FunctionUrlOptions = {}): Promise<string> {
		const { url } = await this.get(options);
		if (isHttpUrl(url)) {
			return url;
		}

		const decryptionKey = options.decryption_key ?? this.decryptionKey;
		if (decryptionKey === undefined) {
			throw new InvalidRequestError(
				"Decryption key is required to decrypt the function download url. Set it when creating the function, i.e. client.NotteFunction({ function_id: '<your-function-id>', decryption_key: '<your-key>' }).",
			);
		}

		let decrypted: string;
		try {
			decrypted = new Encryption(decryptionKey).decrypt(url);
		} catch (error) {
			throw new InvalidRequestError(
				`Failed to decrypt the function download url: ${error instanceof Error ? error.message : String(error)}. Contact support@notte.cc if you need help.`,
			);
		}

		if (!isHttpUrl(decrypted)) {
			throw new NotteError(
				'Failed to decrypt the function download url: the decrypted value is not a URL. Contact support@notte.cc if you need help.',
			);
		}

		return decrypted;
	}

	/**
	 * Download the function code as a python file. Returns the code, and writes
	 * it to `path` when one is provided.
	 *
	 * ```ts
	 * const code = await fn.download({ path: './scraper.py' });
	 * ```
	 */
	async download(options: FunctionDownloadOptions = {}): Promise<string> {
		const { path } = options;
		if (path !== undefined) {
			assertPythonPath(path);
		}

		const url = await this.getUrl(options);

		let response: Response;
		try {
			response = await fetch(url, { signal: AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS) });
		} catch (error) {
			// The url is presigned, so it is deliberately kept out of the message.
			throw new NotteError(
				`Failed to download function code in ${DOWNLOAD_TIMEOUT_MS / 1000} seconds: ${error instanceof Error ? error.message : String(error)}`,
				{ cause: error },
			);
		}

		if (!response.ok) {
			throw new NotteError(`Failed to download function code: ${response.status} ${response.statusText}`);
		}

		const code = await response.text();
		if (path !== undefined) {
			await writeFile(path, code, 'utf8');
		}

		return code;
	}

	/**
	 * Call one of the run endpoints that the OpenAPI spec does not describe
	 * (`FUNCTION_RUN_ENDPOINTS`). The generated client has no operation for
	 * them, so this is the single place where they are hand-rolled; the request
	 * and response shapes are transcribed from `notte_sdk.types`
	 * (`CreateFunctionRunRequest` / `CreateFunctionRunResponse` and
	 * `StartFunctionRunRequest` / `FunctionRunResponse`). Replace the callers
	 * with generated operations once the spec exposes these paths.
	 */
	private async postRunEndpoint<TResponse>(request: FunctionRunEndpointRequest): Promise<TResponse> {
		const response = await this.client.getClient().post<{ 200: TResponse }, unknown, true>({
			url: request.url,
			path: request.path,
			body: request.body,
			headers: { 'Content-Type': 'application/json', ...request.headers },
			parseAs: request.parseAs ?? 'json',
			signal: request.signal,
			throwOnError: true,
		});
		return response.data;
	}
}

function isHttpUrl(value: string): boolean {
	return value.startsWith('https://') || value.startsWith('http://');
}

function assertPythonPath(path: string): void {
	if (!path.endsWith('.py')) {
		throw new InvalidRequestError(`Code file path must end with .py, got '${path}'`);
	}
}

/** Read a local `.py` file into the multipart `file` field the API expects. */
async function readPythonFile(path: string): Promise<File> {
	assertPythonPath(path);
	let bytes: Buffer;
	try {
		bytes = await readFile(path);
	} catch (error) {
		throw new InvalidRequestError(
			`The file '${path}' could not be read: ${error instanceof Error ? error.message : String(error)}`,
		);
	}
	return new File([new Uint8Array(bytes)], basename(path), { type: 'text/x-python' });
}

/**
 * The execution runtime answers authentication failures with its own HTTP
 * envelope (`{ statusCode, headers, body }`) that the API relays with a 200.
 * Surface it as the `NotteAPIError` it really is.
 */
function unwrapRuntimeEnvelope(candidate: Record<string, unknown>, path: string): void {
	const { statusCode, body } = candidate;
	if (typeof statusCode !== 'number' || statusCode < 400 || !('body' in candidate)) {
		return;
	}
	let parsed: unknown = body;
	if (typeof body === 'string') {
		try {
			parsed = JSON.parse(body);
		} catch {
			parsed = body;
		}
	}
	throw NotteAPIError.fromBody(path, statusCode, parsed);
}

/** Validate the shape of a `FunctionRunResponse` returned by the API. */
function parseFunctionRunResult(value: unknown, path: string): FunctionRunResult {
	if (typeof value !== 'object' || value === null) {
		throw new NotteError('Invalid function result: expected an object');
	}
	const candidate = value as Record<string, unknown>;
	unwrapRuntimeEnvelope(candidate, path);
	const status = candidate.status;
	if (
		typeof candidate.function_run_id !== 'string' ||
		typeof candidate.function_id !== 'string' ||
		typeof status !== 'string' ||
		!(FUNCTION_RUN_STATUSES as readonly string[]).includes(status) ||
		!('result' in candidate)
	) {
		throw new NotteError('Invalid function result: missing function_id, function_run_id, status or result');
	}
	return {
		function_id: candidate.function_id,
		function_run_id: candidate.function_run_id,
		session_id: typeof candidate.session_id === 'string' ? candidate.session_id : null,
		result: candidate.result,
		status: status as FunctionRunStatus,
	};
}

/** Consume SSE frames, including frames split across network/UTF-8 boundaries. */
async function readFunctionStream(
	body: ReadableStream<Uint8Array> | null | undefined,
	onLog: (message: string) => void,
	path: string,
	signal?: AbortSignal,
): Promise<FunctionRunResult> {
	if (!body?.getReader) {
		throw new NotteError('Missing function response stream');
	}
	const reader = body.getReader();
	const onAbort = () => {
		reader.cancel(signal?.reason).catch(() => {});
	};
	signal?.addEventListener('abort', onAbort, { once: true });
	const decoder = new TextDecoder();
	let buffer = '';
	let data: string[] = [];
	let result: FunctionRunResult | undefined;
	// Kept only until the first SSE frame arrives, to decode a plain JSON body
	// (for example the runtime's authentication envelope) sent instead of a stream.
	let sawFrame = false;
	let raw = '';
	const dispatch = () => {
		if (!data.length) return;
		const payload = data.join('\n');
		data = [];
		let event: { type?: unknown; message?: unknown };
		try {
			event = JSON.parse(payload) as { type?: unknown; message?: unknown };
		} catch (error) {
			throw new NotteError(`Malformed function stream event: ${payload}`, { cause: error });
		}
		if (event.type === 'log') onLog(String(event.message ?? ''));
		if (event.type === 'error') throw new NotteError(`Function stream error: ${String(event.message ?? '')}`);
		if (event.type === 'result') {
			const value: unknown = typeof event.message === 'string' ? JSON.parse(event.message) : event.message;
			result = parseFunctionRunResult(value, path);
		}
	};
	const line = (value: string) => {
		if (value === '') dispatch();
		else if (value.startsWith('data:')) {
			sawFrame = true;
			data.push(value.slice(5).replace(/^ /, ''));
		}
	};
	try {
		while (true) {
			const { value, done } = await reader.read();
			const text = decoder.decode(value, { stream: !done });
			buffer += text;
			if (!sawFrame) raw += text;
			let end: number;
			while ((end = buffer.indexOf('\n')) !== -1) {
				line(buffer.slice(0, end).replace(/\r$/, ''));
				buffer = buffer.slice(end + 1);
			}
			if (done) break;
		}
		if (buffer) line(buffer.replace(/\r$/, ''));
		dispatch();
		if (!result && !sawFrame && raw.trim().length > 0) {
			let parsed: unknown;
			try {
				parsed = JSON.parse(raw);
			} catch {
				throw new NotteError(`Function stream ended without a result: ${raw.slice(0, 200)}`);
			}
			result = parseFunctionRunResult(parsed, path);
		}
		if (!result) throw new NotteError('Function stream ended without a result');
		return result;
	} finally {
		signal?.removeEventListener('abort', onAbort);
		await reader.cancel().catch(() => {});
		reader.releaseLock();
	}
}
