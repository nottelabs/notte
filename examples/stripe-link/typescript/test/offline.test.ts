import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import Link, { LinkApiError } from '@stripe/link-sdk';
import type { Page } from 'playwright-core';
import { fillApprovedTestCard } from '../src/demo.ts';

const fixture = JSON.parse(readFileSync(new URL('../../test-card.json', import.meta.url), 'utf8'));

async function fill(data: unknown, status = 200) {
  const fields = new Map<string, string>();
  const page = { getByLabel(label: string, options: { exact: boolean }) {
    assert.equal(options.exact, true);
    return {
      async fill(value: string) { fields.set(label, value); },
      async inputValue() { return fields.get(label); },
    };
  } } as unknown as Page;
  const fetchMock: typeof fetch = async (input, options) => {
    const url = new URL(String(input));
    assert.equal(options?.method, 'GET');
    assert.ok(url.pathname.endsWith('/spend_requests/lsrq_notte_fixture'));
    assert.equal(url.searchParams.get('include'), 'card');
    assert.equal(new Headers(options?.headers).get('authorization'), 'Bearer test-link-token');
    return Response.json(data, { status });
  };
  const wallet = new Link({ accessToken: 'test-link-token', fetch: fetchMock });
  await fillApprovedTestCard(page, wallet, fixture.id);
  return fields;
}

test('native SDK requests card expansion and fills the labeled fields', async () => {
  const fields = await fill(fixture);
  assert.deepEqual([...fields.keys()], ['Card number', 'Expiry', 'CVC']);
  assert.equal(fields.get('Expiry'), '12/2030');
  assert.equal(fields.get('Card number'), fixture.card.number);
});

test('unapproved and unknown statuses cannot fill', async () => {
  for (const status of ['created', 'pending_approval', 'denied', 'expired', 'submitted', 'future_status']) {
    await assert.rejects(fill({ ...fixture, status }), /needs approval/);
  }
});

test('missing and non-test credentials cannot fill', async () => {
  await assert.rejects(fill({ ...fixture, card: undefined }), /needs approval/);
  await assert.rejects(fill({ ...fixture, card: { ...fixture.card, number: '4242424242424242' } }), /test-mode/);
  await assert.rejects(fill({ ...fixture, card: { ...fixture.card, cvc: undefined } }), /test-mode/);
});

test('native SDK retains authoritative HTTP rejection', async () => {
  await assert.rejects(fill({ error: { message: 'fixture rejection' } }, 401), (error: unknown) => {
    assert.ok(error instanceof LinkApiError);
    assert.ok(error instanceof Error && 'status' in error);
    assert.equal(error.status, 401);
    return true;
  });
});
