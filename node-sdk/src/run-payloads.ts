import { createHash } from 'node:crypto';
import type { NotteClient } from '@/client';
import type { FunctionRunUpdateRequest, GetFunctionRunResponse } from '@/lib/client/types.gen';

type PayloadField = 'result' | 'logs' | 'variables';
type UploadReference = { upload_id: string; size_bytes: number; sha256: string };
type UploadResponse = { reference: UploadReference; url: string; headers: Record<string, string> };
const INLINE_FIELD_BYTES = 1024 * 1024;
const MAX_PAYLOAD_BYTES = 256 * 1024 * 1024;

/** Upload large fields before sending the run's final metadata update. */
export async function offloadRunPayloads(
	client: ReturnType<NotteClient['getClient']>,
	path: { function_id: string; run_id: string },
	fields: FunctionRunUpdateRequest,
): Promise<Record<string, unknown>> {
	const data: Record<string, unknown> = { ...fields };
	const references: Partial<Record<PayloadField, UploadReference>> = {};
	// The persisted result and read contract are text, including structured results.
	if (data.result != null && typeof data.result !== 'string') data.result = JSON.stringify(data.result);
	for (const field of ['result', 'logs', 'variables'] as const) {
		if (data[field] == null) continue;
		const payload = Buffer.from(JSON.stringify(data[field]), 'utf8');
		if (payload.length > MAX_PAYLOAD_BYTES) throw new Error(`Function run ${field} exceeds the payload limit`);
		if (payload.length <= INLINE_FIELD_BYTES) continue;
		const checksum = createHash('sha256').update(payload).digest('base64');
		const prepared = await client.post<{ 200: UploadResponse }, unknown, true>({
			url: '/functions/{function_id}/runs/{run_id}/payloads/{field}/upload',
			path: { ...path, field },
			body: { size_bytes: payload.length, sha256: checksum },
			headers: { 'Content-Type': 'application/json' },
			throwOnError: true,
		});
		const upload = prepared.data;
		if (upload.reference.size_bytes !== payload.length || upload.reference.sha256 !== checksum) {
			throw new Error('Run payload upload reference does not match the local payload');
		}
		if (new URL(upload.url).protocol !== 'https:') throw new Error('Invalid run payload URL');
		// This request bypasses the authenticated API client and cannot follow redirects.
		const response = await fetch(upload.url, {
			method: 'PUT', body: payload, headers: upload.headers,
			redirect: 'error', signal: AbortSignal.timeout(300_000),
		});
		await response.body?.cancel();
		if (!response.ok) throw new Error(`Run payload upload failed (${response.status})`);
		references[field] = upload.reference;
		if (field === 'result' && typeof data.result === 'string') data.result_preview = data.result.slice(0, 16000);
		delete data[field];
	}
	if (Object.keys(references).length) data.payloads = references;
	return data;
}

export type RunWithPayloads = GetFunctionRunResponse & {
	payloads?: Partial<Record<PayloadField, { size_bytes: number; sha256: string }>>;
	payload_urls?: Partial<Record<PayloadField, string>>;
};

/** Decode large fields on the client, never through API JSON buffering. */
export async function resolveRunPayloads(input: RunWithPayloads): Promise<GetFunctionRunResponse> {
	const run = { ...input };
	for (const [field, reference] of Object.entries(run.payloads ?? {})) {
		if (!['result', 'logs', 'variables'].includes(field)) throw new Error('Unknown run payload field');
		if (!Number.isSafeInteger(reference.size_bytes) || reference.size_bytes <= 0 || reference.size_bytes > 256 * 1024 * 1024) {
			throw new Error('Invalid run payload size');
		}
		const url = run.payload_urls?.[field as PayloadField];
		if (!url || new URL(url).protocol !== 'https:') throw new Error('Invalid run payload URL');
		// Use a separate fetch so API authentication and preview headers cannot
		// follow the signed URL to storage.
		const response = await fetch(url, { redirect: 'error', signal: AbortSignal.timeout(300_000) });
		if (!response.ok || !response.body) throw new Error(`Run payload download failed (${response.status})`);
		const reader = response.body.getReader();
		const chunks: Uint8Array[] = [];
		const hash = createHash('sha256');
		let size = 0;
		try {
			while (true) {
				const { done, value } = await reader.read();
				if (done) break;
				size += value.length;
				if (size > reference.size_bytes) throw new Error('Run payload exceeds its declared size');
				hash.update(value);
				chunks.push(value);
			}
		} finally {
			await reader.cancel();
			reader.releaseLock();
		}
		if (size !== reference.size_bytes || hash.digest('base64') !== reference.sha256) {
			throw new Error('Run payload failed size/checksum verification');
		}
		const value: unknown = JSON.parse(Buffer.concat(chunks, size).toString('utf8'));
		if (field === 'result' && value !== null && typeof value !== 'string') throw new Error('Invalid stored result');
		if (field === 'logs' && (!Array.isArray(value) || !value.every(line => typeof line === 'string'))) throw new Error('Invalid stored logs');
		if (field === 'variables' && value !== null && (typeof value !== 'object' || Array.isArray(value))) throw new Error('Invalid stored variables');
		Object.assign(run, { [field]: value });
	}
	delete run.payloads;
	delete run.payload_urls;
	return run;
}
