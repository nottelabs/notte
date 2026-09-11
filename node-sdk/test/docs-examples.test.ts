import { describe, expect, it } from 'vitest';
import {
  collectExampleResult,
  verifyExampleOutput,
} from './helpers/docs-examples';

describe('paired example output contracts', () => {
  it('checks timeout bounds only when the example explicitly demonstrates them', () => {
    const status = {
      session_id: 'owned-session',
      status: 'active',
      idle_timeout_minutes: 15,
      max_duration_minutes: 20,
    };
    const ordinary = { expected: { status: 'active' }, closedSession: true };
    expect(collectExampleResult({ status }, ordinary)).toEqual({
      session_id: 'owned-session',
      status: 'active',
    });
    const timeout = {
      expected: { status: 'active', idle_timeout_minutes: 15, max_duration_minutes: 20 },
      closedSession: true,
    };
    expect(collectExampleResult({ status }, timeout).idle_timeout_minutes).toBe(
      15,
    );
    expect(collectExampleResult({ status }, timeout).max_duration_minutes).toBe(20);
  });

  it('collects SDK return values without requiring prints in the example', () => {
    const contract = {
      expected: { status: 'closed', result: { url: 'https://example.com' } },
    };
    const result = { status: 'closed', result: { url: 'https://example.com' } };
    expect(collectExampleResult({ result }, contract)).toEqual(
      contract.expected,
    );
    expect(() => collectExampleResult({}, contract)).toThrow(
      'Missing example response',
    );
  });

  it('does not accept two missing run IDs as a successful metadata check', () => {
    const contract = { expected: { status: 'closed', same_run: true } };
    expect(() =>
      collectExampleResult({ run_status: { status: 'closed' } }, contract),
    ).toThrow();
    expect(
      collectExampleResult(
        {
          run_id: 'owned-run',
          run_status: { status: 'closed', function_run_id: 'other-run' },
        },
        contract,
      ).same_run,
    ).toBe(false);
  });

  const sessionId = '12345678-1234-1234-1234-123456789012';
  const contract = {
    expected: { title: 'Example Domain' },
    closedSession: true,
  };

  it('returns the owned session ID for remote cleanup verification', () => {
    expect(
      verifyExampleOutput(
        JSON.stringify({ session_id: sessionId, title: 'Example Domain' }),
        contract,
      ),
    ).toBe(sessionId);
  });

  it.each([
    '',
    'script exited without a result',
    'null',
    '[]',
    JSON.stringify({ title: 'Example Domain' }),
    JSON.stringify({ session_id: 'placeholder', title: 'Example Domain' }),
    JSON.stringify({ session_id: sessionId, title: 'Wrong task' }),
    JSON.stringify({
      session_id: sessionId,
      title: 'Example Domain',
      unexpected: true,
    }),
  ])('rejects missing or unequal behavior: %s', (output) => {
    expect(() => verifyExampleOutput(output, contract)).toThrow();
  });

  it('requires the streaming example to emit its function log as well as its result', () => {
    const stream = {
      expected: { status: 'closed' },
      logContains: 'Running docs echo',
    };
    expect(() => verifyExampleOutput('{"status":"closed"}', stream)).toThrow();
    expect(
      verifyExampleOutput('Running docs echo\n{"status":"closed"}\n', stream),
    ).toBeUndefined();
    // Python's SDK writes live logs to stderr and the example's result to stdout.
    expect(
      verifyExampleOutput(
        '{"status":"closed"}',
        stream,
        'INFO Running docs echo',
      ),
    ).toBeUndefined();
  });
});
