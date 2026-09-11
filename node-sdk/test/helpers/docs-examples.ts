import assert from 'node:assert/strict';

export interface ExampleContract {
  expected: Record<string, unknown>;
  closedSession?: boolean;
  logContains?: string;
}

/** Read runtime values exported by TS or collected with runpy for Python. */
export function collectExampleResult(
  values: Record<string, unknown>,
  contract: ExampleContract,
): Record<string, unknown> {
  const record = (value: unknown): Record<string, unknown> => {
    assert.ok(
      value !== null && typeof value === 'object' && !Array.isArray(value),
      'Missing example response',
    );
    return value as Record<string, unknown>;
  };
  if (contract.closedSession) {
    if ('error' in contract.expected)
      return { session_id: values.session_id, error: values.error_message };
    const status = record(values.status);
    return {
      session_id: status.session_id,
      status: status.status,
      ...('idle_timeout_minutes' in contract.expected
        ? { idle_timeout_minutes: status.idle_timeout_minutes }
        : {}),
      ...('max_duration_minutes' in contract.expected
        ? { max_duration_minutes: status.max_duration_minutes }
        : {}),
      ...('title' in contract.expected ? { title: values.title } : {}),
      ...('viewport' in contract.expected ? { viewport: values.viewport } : {}),
    };
  }
  if ('same_run' in contract.expected) {
    const run = record(values.run_status);
    assert.equal(typeof values.run_id, 'string', 'Missing executed run ID');
    return {
      status: run.status,
      same_run: run.function_run_id === values.run_id,
    };
  }
  if ('results' in contract.expected) return { results: values.results };
  const result = record(values.result);
  return {
    status: result.status,
    ...('result' in contract.expected ? { result: result.result } : {}),
  };
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
