/**
 * Remote counterpart of the `raise_on_failure` gate: the action runs server
 * side, the `ApiExecutionResponse` is serialised to JSON and rebuilt client
 * side, and only then is the raise gate evaluated. Mirrors
 * `tests/sdk/test_execute_raise_on_failure.py`.
 */
import { beforeEach, describe, it, expect, expectTypeOf, vi } from 'vitest';
import { CAPTCHA_SOLVE_TIMEOUT_MS, Session } from '@/session';
import { TIMEOUT_HEADER } from '@/client';
import { actions, type ExecuteAction } from '@/actions';
import { ActionExecutionError, NotteAPIError, NotteError } from '@/errors';
import { pageExecute, sessionStart } from '@/lib/client/sdk.gen';
import type { ApiExecutionResponse, SerializedError } from '@/lib/client/types.gen';
import { executionResult, mockNotteClient, overTheWire, serializedError, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
  pageExecute: vi.fn(),
}));

const TIMEOUT_MESSAGE = 'JavaScript evaluation timed out after 45000ms';
const ACTION = actions.evaluateJs({ code: 'new Promise(() => {})' });

/** The `ApiExecutionResponse` the API builds after a failed `evaluate_js` action. */
function serverSideResult(detail: SerializedError | null): ApiExecutionResponse {
  return executionResult({
    action: ACTION,
    success: false,
    message: TIMEOUT_MESSAGE,
    data: null,
    exception: detail ? detail.dev_message : null,
    exception_detail: detail,
  });
}

async function remoteSession(result: ApiExecutionResponse, options: { raiseOnFailure?: boolean } = {}): Promise<Session> {
  vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse() } as never);
  vi.mocked(pageExecute).mockResolvedValue({ data: result } as never);
  const session = new Session(mockNotteClient(), options);
  await session.start();
  return session;
}

describe('execute raise on failure', () => {
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.resetAllMocks();
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  it.each(['developer', 'user'] as const)('rehydrates the typed error with the actual reason (%s mode)', async mode => {
    // whatever error mode the API serialises with, every audience message carries the real reason
    const detail = serializedError({
      dev_message:
        mode === 'developer'
          ? `Failed to execute action 'evaluate_js' in url https://example.com: ${TIMEOUT_MESSAGE}`
          : `${TIMEOUT_MESSAGE}. Check the action parameters.`,
      user_message: `The action could not be executed: ${TIMEOUT_MESSAGE}`,
      agent_message: TIMEOUT_MESSAGE,
      should_retry_later: true,
    });
    const session = await remoteSession(overTheWire(serverSideResult(detail)));

    const error = await session.execute(ACTION).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ActionExecutionError);
    expect(error).toBeInstanceOf(NotteError);
    const typed = error as ActionExecutionError;
    expect(typed.errorType).toBe('ActionExecutionError');
    expect(typed.message).toContain(TIMEOUT_MESSAGE);
    expect(typed.devMessage).toBe(detail.dev_message);
    expect(typed.userMessage).toBe(detail.user_message);
    expect(typed.agentMessage).toBe(TIMEOUT_MESSAGE);
    expect(typed.shouldRetryLater).toBe(true);
    expect(errorSpy).toHaveBeenCalledWith(`🚨 Execution failed with message: '${TIMEOUT_MESSAGE}'`);
  });

  it('does not raise when disabled per call and still returns a result that says it failed', async () => {
    const session = await remoteSession(overTheWire(serverSideResult(serializedError({ dev_message: TIMEOUT_MESSAGE }))));

    const result = await session.execute(ACTION, { raiseOnFailure: false });

    expect(result.success).toBe(false);
    expect(result.data).toBeNull();
    expect(result.message).toBe(TIMEOUT_MESSAGE);
    expect(result.exception_detail?.error_type).toBe('ActionExecutionError');
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('keeps the legacy positional boolean argument', async () => {
    const session = await remoteSession(overTheWire(serverSideResult(serializedError())));
    const result = await session.execute(ACTION, false);
    expect(result.success).toBe(false);
  });

  it('still raises a failure the API reports without an exception', async () => {
    // the API may report a failure without attaching an exception: still raise the reason
    const session = await remoteSession(overTheWire(serverSideResult(null)));

    const error = await session.execute(ACTION).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ActionExecutionError);
    expect((error as ActionExecutionError).errorType).toBe('NotteBaseError');
    expect((error as Error).message).toContain(TIMEOUT_MESSAGE);
  });

  it('falls back to the action type when the API sends an empty message', async () => {
    const session = await remoteSession(overTheWire(executionResult({ action: ACTION, success: false, message: '  ' })));
    await expect(session.execute(ACTION)).rejects.toThrow('Failed to execute action: evaluate_js');
  });

  it('is quiet when disabled at the session level', async () => {
    const session = await remoteSession(overTheWire(serverSideResult(null)), { raiseOnFailure: false });

    const result = await session.execute(ACTION);

    expect(result.success).toBe(false);
    expect(result.exception_detail).toBeNull();
    expect(result.message).toBe(TIMEOUT_MESSAGE);
  });

  it('lets a per-call raiseOnFailure override the session default', async () => {
    const session = await remoteSession(overTheWire(serverSideResult(serializedError())), { raiseOnFailure: false });
    await expect(session.execute(ACTION, { raiseOnFailure: true })).rejects.toBeInstanceOf(ActionExecutionError);
    await expect(session.execute(ACTION, true)).rejects.toBeInstanceOf(ActionExecutionError);
  });

  it('returns successful results untouched', async () => {
    const result = executionResult({ action: actions.goto({ url: 'https://example.com' }) });
    const session = await remoteSession(overTheWire(result));

    expect(await session.execute({ type: 'goto', url: 'https://example.com' })).toEqual(result);
    expect(pageExecute).toHaveBeenCalledWith(
      expect.objectContaining({ path: { session_id: 'session-123' }, body: { type: 'goto', url: 'https://example.com' } }),
    );
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('rejects when the session is not started', async () => {
    await expect(new Session(mockNotteClient()).execute(ACTION)).rejects.toThrow('Session not started');
    expect(pageExecute).not.toHaveBeenCalled();
  });

  it('is typed against the generated action union', () => {
    expectTypeOf<Parameters<Session['execute']>[0]>().toEqualTypeOf<ExecuteAction>();
    expectTypeOf<Awaited<ReturnType<Session['execute']>>>().toEqualTypeOf<ApiExecutionResponse>();
    // @ts-expect-error unknown action types are rejected at compile time
    void ((s: Session) => s.execute({ type: 'teleport' }));
    // @ts-expect-error a goto action needs a url
    void ((s: Session) => s.execute({ type: 'goto' }));
  });

  describe('captcha solve', () => {
    const CAPTCHA = actions.captchaSolve({ captcha_type: 'recaptcha' });
    const timeout = () => new NotteAPIError('/sessions/session-123/page/execute', 408, { message: 'Request Timeout' });

    it('uses the long request timeout header', async () => {
      const session = await remoteSession(executionResult({ action: CAPTCHA }));
      await session.execute(CAPTCHA);
      expect(CAPTCHA_SOLVE_TIMEOUT_MS).toBe(100_000);
      expect(pageExecute).toHaveBeenCalledWith(expect.objectContaining({ headers: { [TIMEOUT_HEADER]: '100000' } }));
    });

    it('does not set the header for other actions', async () => {
      const session = await remoteSession(executionResult());
      await session.execute(actions.goto({ url: 'https://example.com' }));
      expect(pageExecute).toHaveBeenCalledWith(expect.objectContaining({ headers: undefined }));
    });

    it('retries on 408 and returns the eventual result', async () => {
      const session = await remoteSession(executionResult({ action: CAPTCHA }));
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      vi.mocked(pageExecute)
        .mockRejectedValueOnce(timeout())
        .mockRejectedValueOnce(timeout())
        .mockResolvedValueOnce({ data: executionResult({ action: CAPTCHA }) } as never);

      expect((await session.execute(CAPTCHA)).success).toBe(true);
      expect(pageExecute).toHaveBeenCalledTimes(3);
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('Solve captcha action timed out'));
    });

    it('gives up after three timeouts', async () => {
      const session = await remoteSession(executionResult({ action: CAPTCHA }));
      vi.mocked(pageExecute).mockRejectedValue(timeout());

      const error = await session.execute(CAPTCHA).catch((e: unknown) => e);
      expect(error).toBeInstanceOf(NotteAPIError);
      expect((error as NotteAPIError).statusCode).toBe(408);
      expect(pageExecute).toHaveBeenCalledTimes(3);
    });

    it('does not retry other actions or other status codes', async () => {
      const session = await remoteSession(executionResult());
      vi.mocked(pageExecute).mockRejectedValue(timeout());
      await expect(session.execute(actions.goto({ url: 'https://example.com' }))).rejects.toBeInstanceOf(NotteAPIError);
      expect(pageExecute).toHaveBeenCalledTimes(1);

      vi.mocked(pageExecute).mockClear();
      vi.mocked(pageExecute).mockRejectedValue(new NotteAPIError('/execute', 500, {}));
      await expect(session.execute(CAPTCHA)).rejects.toBeInstanceOf(NotteAPIError);
      expect(pageExecute).toHaveBeenCalledTimes(1);
    });
  });
});
