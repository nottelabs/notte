import assert from 'node:assert/strict';

export interface ExampleContract {
  expected: Record<string, unknown>;
  closedSession?: boolean;
  logContains?: string;
}

/** Compare actual example output, not a rewritten or mocked version of the script. */
export function verifyExampleOutput(
  output: string,
  contract: ExampleContract,
  logs: string = output,
): string | undefined {
  const lines = output.trim().split(/\r?\n/);
  const result: unknown = JSON.parse(lines.at(-1) || '');
  assert.ok(
    result !== null && typeof result === 'object' && !Array.isArray(result),
    'Expected a JSON object',
  );
  const values = { ...result } as Record<string, unknown>;
  let sessionId: string | undefined;
  if (contract.closedSession) {
    assert.match(
      String(values.session_id),
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );
    sessionId = String(values.session_id);
    delete values.session_id;
  }
  assert.deepStrictEqual(values, contract.expected);
  if (contract.logContains)
    assert.ok(
      logs.includes(contract.logContains),
      'Expected streamed function log',
    );
  return sessionId;
}
