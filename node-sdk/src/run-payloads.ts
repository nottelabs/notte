import { createHash } from 'node:crypto';
import type { GetFunctionRunResponse } from '@/lib/client/types.gen';

type PayloadField = 'result' | 'logs' | 'variables';
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
