import assert from 'node:assert/strict';
import { test, mock } from 'node:test';
import OpenAI from 'openai';
import type { Page } from 'playwright-core';
import { NotteComputer } from '../src/computer.ts';

test('stateless turns replay reasoning, native actions and screenshots', async () => {
  const payloads: { model: string; store: boolean; include: string[]; tools: unknown; provider: unknown; input: Record<string, unknown>[] }[] = [];
  const fetch = mock.fn<typeof globalThis.fetch>(async (_url, init) => {
    assert.equal(new Headers(init?.headers).get('Authorization'), 'Bearer fixture-router-key');
    payloads.push(JSON.parse(String(init?.body)));
    const turn = payloads.length;
    const output = [];
    if (turn === 1) output.push({ id: 'rs_1', type: 'reasoning', summary: [], encrypted_content: 'opaque' });
    if (turn <= 2) output.push({ id: `cu_${turn}`, type: 'computer_call', call_id: `call_${turn}`, status: 'completed', actions: [{ type: 'screenshot' }], pending_safety_checks: [] });
    return new Response(JSON.stringify({ id: `resp_${turn}`, object: 'response', created_at: 0, model: 'openai/gpt-6.1-sol', status: 'completed', output }), { headers: { 'Content-Type': 'application/json' } });
  });
  const page = {
    viewportSize: () => ({ width: 1024, height: 768 }),
    screenshot: async () => Buffer.from('fixture-png'),
  } as Page;
  const computer = new NotteComputer(page, () => true);
  await computer.run(new OpenAI({ apiKey: 'fixture-router-key', baseURL: 'https://router.invalid/v1', fetch, maxRetries: 0 }), 'Read the screen'); // pragma: allowlist secret
  assert.equal(payloads.length, 3);
  assert.deepEqual(computer.actions, ['screenshot', 'screenshot']);
  for (const payload of payloads) {
    assert.equal(payload.model, 'openai/gpt-6.1-sol');
    assert.deepEqual(payload.tools, [{ type: 'computer' }]);
    assert.equal(payload.store, false);
    assert.deepEqual(payload.include, ['reasoning.encrypted_content']);
    assert.deepEqual(payload.provider, { allow_fallbacks: false });
    assert.equal('previous_response_id' in payload, false);
  }
  assert.deepEqual(payloads[2].input.map(item => item.type ?? item.role), ['user', 'reasoning', 'computer_call', 'computer_call_output', 'computer_call', 'computer_call_output']);
  assert.equal(payloads[2].input[1].encrypted_content, 'opaque');
  assert.deepEqual(payloads[2].input.slice(0, 4), payloads[1].input);
  for (const [index, turn] of [[3, 1], [5, 2]]) assert.deepEqual(payloads[2].input[index], {
    type: 'computer_call_output', call_id: `call_${turn}`,
    output: { type: 'computer_screenshot', image_url: 'data:image/png;base64,Zml4dHVyZS1wbmc=', detail: 'original' },
  });
});
