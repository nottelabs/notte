import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import { parseAgentStatusMessage, prepareAgentRequest } from '@/agent';

// Mirrors python-sdk tests/test_response_format.py — validates that
// Zod schemas are converted to JSON Schema on request, and that the
// returned zodSchema enforces the same constraints at runtime.

const ProductSchema = z.object({
  name: z.string(),
  price: z.number().int().min(0).max(5),
});

const ProductResponseSchema = z.object({
  products: z.array(z.record(z.string(), ProductSchema)).min(2).max(3),
  total_price: z
    .string()
    .default('')
    .describe('Final amount to be paid including all components'),
});

describe('prepareAgentRequest', () => {
  it('converts a Zod response_format to JSON Schema and returns the zodSchema', () => {
    const { apiData, zodSchema } = prepareAgentRequest({
      task: 't',
      response_format: ProductResponseSchema,
    } as any);

    expect(zodSchema).not.toBeNull();
    // The outbound payload must be a plain JSON Schema, not the Zod instance.
    expect(apiData.response_format).toBeDefined();
    const js: any = apiData.response_format;
    expect(typeof js).toBe('object');
    expect(typeof (js as any).parse).toBe('undefined');
    expect(js.type).toBe('object');
    expect(js.properties).toBeDefined();
    expect(js.properties.products).toBeDefined();
    expect(js.properties.products.minItems).toBe(2);
    expect(js.properties.products.maxItems).toBe(3);
  });

  it('returns null zodSchema and leaves response_format untouched when it is not Zod', () => {
    const raw = { type: 'object', properties: {} };
    const { apiData, zodSchema } = prepareAgentRequest({
      task: 't',
      response_format: raw,
    } as any);
    expect(zodSchema).toBeNull();
    expect(apiData.response_format).toBe(raw);
  });

  it('handles missing response_format', () => {
    const { apiData, zodSchema } = prepareAgentRequest({ task: 't' } as any);
    expect(zodSchema).toBeNull();
    expect(apiData.response_format).toBeUndefined();
  });
});

describe('parseAgentStatusMessage', () => {
  const finalStatus = {
    agent_id: 'agent-123',
    created_at: '2026-05-21T20:27:22.000Z',
    session_id: 'session-123',
    status: 'closed',
    task: 'check email',
    success: true,
    answer: 'No new messages',
    steps: [],
  };

  it('parses the wrapped agent_stop websocket message', () => {
    expect(parseAgentStatusMessage({ status: 'agent_stop', agent: finalStatus }, 'agent-123')).toEqual(finalStatus);
  });

  it('parses the legacy raw status websocket message', () => {
    expect(parseAgentStatusMessage(finalStatus, 'agent-123')).toEqual(finalStatus);
  });

  it('ignores step messages and statuses for other agents', () => {
    expect(parseAgentStatusMessage({ type: 'agent_step_start', value: {} }, 'agent-123')).toBeNull();
    expect(parseAgentStatusMessage({ status: 'agent_stop', agent: finalStatus }, 'agent-456')).toBeNull();
  });
});

describe('Zod schema runtime validation (mirrors python test_response_format)', () => {
  const validOutput = JSON.stringify({
    products: [
      { a: { name: 'a', price: 5 } },
      { b: { name: 'bprod', price: 3 } },
    ],
    total_price: '5',
  });

  const wrongTypeOutput = JSON.stringify({
    products: [
      { a: { name: 'a', price: 5 } },
      { b: { name: 'bprod', price: -1 } },
    ],
    total_price: 5,
  });

  const tooShortOutput = JSON.stringify({
    products: [{ a: { name: 'a', price: 5 } }],
    total_price: '5',
  });

  const geViolationOutput = JSON.stringify({
    products: [
      { a: { name: 'a', price: 5 } },
      { b: { name: 'bprod', price: -1 } },
    ],
    total_price: '-1',
  });

  it('accepts an in-constraints answer', () => {
    const result = ProductResponseSchema.safeParse(JSON.parse(validOutput));
    expect(result.success).toBe(true);
  });

  it('rejects wrong types (total_price number, price ge violation)', () => {
    const result = ProductResponseSchema.safeParse(JSON.parse(wrongTypeOutput));
    expect(result.success).toBe(false);
  });

  it('rejects arrays below min_length', () => {
    const result = ProductResponseSchema.safeParse(JSON.parse(tooShortOutput));
    expect(result.success).toBe(false);
  });

  it('rejects ge (min) violation on nested field', () => {
    const result = ProductResponseSchema.safeParse(JSON.parse(geViolationOutput));
    expect(result.success).toBe(false);
  });
});
