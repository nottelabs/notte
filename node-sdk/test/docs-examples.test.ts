import { describe, expect, it } from 'vitest';
import { verifyExampleOutput } from './helpers/docs-examples';

describe('paired example output contracts', () => {
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
