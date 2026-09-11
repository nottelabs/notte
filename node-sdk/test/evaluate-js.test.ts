/** Remote `evaluateJs()`: the string on success, the typed throw on failure. Mirrors `tests/sdk/test_evaluate_js_helper.py`. */
import { beforeEach, describe, it, expect, expectTypeOf, vi } from 'vitest';
import { Session } from '@/session';
import { ActionExecutionError, EvaluateJsNoDataError } from '@/errors';
import { pageExecute, sessionStart } from '@/lib/client/sdk.gen';
import type { ApiExecutionResponse, SerializedError } from '@/lib/client/types.gen';
import { executionResult, mockNotteClient, overTheWire, serializedError, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
  pageExecute: vi.fn(),
}));

const CODE = '1 + 1';

function evalResult(options: { success: boolean; markdown?: string; detail?: SerializedError }): ApiExecutionResponse {
  return executionResult({
    action: { type: 'evaluate_js', code: CODE },
    success: options.success,
    message: options.success ? 'ok' : 'JavaScript evaluation failed: boom',
    data: options.markdown !== undefined ? { markdown: options.markdown } : null,
    exception_detail: options.detail ?? null,
  });
}

async function remoteSession(result: ApiExecutionResponse): Promise<Session> {
  vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse() } as never);
  vi.mocked(pageExecute).mockResolvedValue({ data: result } as never);
  const session = new Session(mockNotteClient());
  await session.start();
  return session;
}

describe('evaluateJs', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('returns the string', async () => {
    const session = await remoteSession(overTheWire(evalResult({ success: true, markdown: '2' })));
    expect(await session.evaluateJs(CODE)).toBe('2');
    expect(pageExecute).toHaveBeenCalledWith(expect.objectContaining({ body: { type: 'evaluate_js', code: CODE } }));
  });

  it('raises the typed error on failure', async () => {
    const detail = serializedError({ dev_message: "Failed to execute action 'evaluate_js' in url https://example.com: boom" });
    const session = await remoteSession(overTheWire(evalResult({ success: false, detail })));
    await expect(session.evaluateJs(CODE)).rejects.toBeInstanceOf(ActionExecutionError);
  });

  it('returns the envelope when not raising', async () => {
    const session = await remoteSession(overTheWire(evalResult({ success: false })));
    const result = await session.evaluateJs(CODE, { raiseOnFailure: false });
    expect(result.success).toBe(false);
    expect(result.message).toBe('JavaScript evaluation failed: boom');
  });

  it('raises instead of returning undefined when success comes without data', async () => {
    // an API build that predates the eval-js fix can report success with no data
    const session = await remoteSession(overTheWire(evalResult({ success: true })));
    await expect(session.evaluateJs(CODE)).rejects.toBeInstanceOf(EvaluateJsNoDataError);
    await expect(session.evaluateJs(CODE)).rejects.toThrow('returned no data');
  });

  it('is typed by raiseOnFailure', () => {
    void ((s: Session) => {
      expectTypeOf(s.evaluateJs(CODE)).toEqualTypeOf<Promise<string>>();
      expectTypeOf(s.evaluateJs(CODE, { raiseOnFailure: true })).toEqualTypeOf<Promise<string>>();
      expectTypeOf(s.evaluateJs(CODE, { raiseOnFailure: false })).toEqualTypeOf<Promise<ApiExecutionResponse>>();
    });
  });
});
