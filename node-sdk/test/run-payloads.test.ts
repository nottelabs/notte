import { createHash } from 'node:crypto';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { resolveRunPayloads, type RunWithPayloads } from '@/run-payloads';

const raw = JSON.stringify(['first', 'second']);
function run(): RunWithPayloads {
	return {
		function_id: 'fn', function_run_id: 'run', workflow_id: 'fn', workflow_run_id: 'run', status: 'closed',
		created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', logs: [],
		payloads: { logs: { size_bytes: Buffer.byteLength(raw), sha256: createHash('sha256').update(raw).digest('base64') } },
		payload_urls: { logs: 'https://storage.example/object' },
	};
}

describe('run payload download', () => {
	afterEach(() => vi.unstubAllGlobals());
	it('checks bytes and downloads without API credentials', async () => {
		const fetcher = vi.fn().mockResolvedValue(new Response(raw));
		vi.stubGlobal('fetch', fetcher);
		const result = await resolveRunPayloads(run());
		expect(result.logs).toEqual(['first', 'second']);
		expect(result).not.toHaveProperty('payloads');
		expect(fetcher.mock.calls[0][1]).not.toHaveProperty('headers');
		expect(fetcher.mock.calls[0][1].redirect).toBe('error');
	});
	it.each([raw + ' ', raw.slice(1), raw.replace('first', 'wrong')])('rejects incorrect bytes', async bytes => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(bytes)));
		await expect(resolveRunPayloads(run())).rejects.toThrow(/size|checksum/);
	});
	it('fails on an unavailable payload instead of returning empty logs', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })));
		await expect(resolveRunPayloads(run())).rejects.toThrow('download failed');
	});
});
