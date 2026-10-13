/**
 * Mirrors the session part of `tests/integration/sdk/test_steps.py`: manual
 * execute/observe calls are recorded as session steps in order. The agent part
 * of the Python test is not mirrored because agents are being removed from the
 * Node SDK (see PYTHON_PARITY.md section 4).
 */
import { beforeEach, describe, it, expect } from 'vitest';
import { NotteClient } from '@/client';
import { actions } from '@/actions';

import { config } from 'dotenv';
config();

type Step = { type?: string; value?: { action?: { type?: string } } };

describe('Steps Integration Tests', () => {
  let client: NotteClient;

  beforeEach(() => {
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
  });

  it('records execute and observe calls as session steps', { timeout: 90_000 }, async () => {
    const session = client.Session({ proxies: false, open_viewer: false });
    await session.use(async s => {
      await s.execute(actions.goto({ url: 'https://example.com' }));
      await s.observe();
      await s.execute(actions.goto({ url: 'https://example.org' }));
    });

    // steps may be written asynchronously; retry status() a few times
    let steps: Step[] = [];
    for (let attempt = 0; attempt < 5 && steps.length < 3; attempt += 1) {
      steps = ((await session.status()).steps ?? []) as Step[];
      if (steps.length < 3) await new Promise(resolve => setTimeout(resolve, 300));
    }

    expect(steps.length).toBeGreaterThanOrEqual(3);
    expect(steps[0].type).toBe('execution_result');
    expect(steps[1].type).toBe('observation');
    expect(steps[0].value?.action?.type).toBe('goto');

    const executionResults = steps.filter(step => step.type === 'execution_result' && step.value?.action);
    expect(executionResults.length).toBeGreaterThanOrEqual(2);
    expect(executionResults[executionResults.length - 1].value?.action?.type).toBe('goto');
  });
});
