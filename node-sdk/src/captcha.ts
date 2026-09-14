import type { ApiExecutionResponse } from '@/lib/client/types.gen';
import type { ExecuteAction } from '@/actions';
import { NotteAPIError, NotteTimeoutError, sleep } from '@/errors';

export interface CaptchaStatus {
  captcha_id: string;
  page_id: string;
  generation: number;
  state: 'solving' | 'solved' | 'failed' | 'cancelled';
  retry_after_ms: number;
  message?: string;
}

/** Execution envelope with the backend's additive CAPTCHA coordination fields. */
export type CaptchaExecutionResponse = ApiExecutionResponse & {
  captcha?: CaptchaStatus | null;
  action_executed?: boolean | null;
  code?: string | null;
};

export interface CaptchaExecuteParams {
  captcha_timeout_seconds: number;
  captcha_id?: string;
  target_page_id?: string;
  target_generation?: number;
}

/** Poll background work; only an explicit unexecuted response permits action resubmission. */
export async function executeWithCaptcha(
  action: ExecuteAction,
  budgetSeconds: number,
  request: (action: ExecuteAction, params: CaptchaExecuteParams, timeoutMs?: number) => Promise<CaptchaExecutionResponse>,
): Promise<CaptchaExecutionResponse> {
  const explicit = action.type === 'captcha_solve';
  let deadline = explicit ? performance.now() + budgetSeconds * 1000 : undefined;
  let params: CaptchaExecuteParams = { captcha_timeout_seconds: budgetSeconds };
  let requestAction = action;
  let original: CaptchaExecutionResponse | undefined;
  let last: CaptchaExecutionResponse | undefined;
  const remaining = () => deadline === undefined ? budgetSeconds : (deadline - performance.now()) / 1000;
  const pause = (ms = 1000) => sleep(Math.max(0, Math.min(ms, remaining() * 1000)));
  const failure = (message: string, code: string): CaptchaExecutionResponse => ({
    started_at: new Date().toISOString(), ended_at: new Date().toISOString(),
    ...(original ?? last), action, success: false, message, code,
    exception: message, exception_detail: null, captcha: last?.captcha,
  });
  while (true) {
    const left = remaining();
    if (left <= 0) return failure('CAPTCHA wait deadline exceeded', 'captcha_timeout');
    params.captcha_timeout_seconds = left;
    const polling = requestAction.type === 'captcha_solve';
    let result: CaptchaExecutionResponse;
    try {
      result = await request(requestAction, { ...params }, polling ? Math.min(10_000, left * 1000) : undefined);
    } catch (error) {
      const transport = error instanceof NotteTimeoutError || error instanceof TypeError || error instanceof SyntaxError;
      const transient = params.captcha_id !== undefined && error instanceof NotteAPIError &&
        [408, 429, 502, 503, 504].includes(error.statusCode);
      if (!polling || (!transport && !transient)) throw error;
      await pause();
      continue;
    }
    last = result;
    const status = result.captcha;
    if (!status) {
      return params.captcha_id ? failure('Server omitted CAPTCHA polling status', 'captcha_protocol_error') : result;
    }
    if (params.captcha_id && status.captcha_id !== params.captcha_id) {
      return failure('Server returned a different CAPTCHA solve', 'captcha_protocol_error');
    }
    deadline ??= performance.now() + budgetSeconds * 1000;
    if (!original && !explicit && result.action_executed === true) original = result;
    if (status.state === 'failed' || status.state === 'cancelled') {
      return failure(status.message || `CAPTCHA ${status.state}`, `captcha_${status.state}`);
    }
    if (status.state === 'solved') {
      if (explicit) return result;
      if (original) return { ...original, captcha: status };
      if (!params.captcha_id && result.action_executed !== false) return result;
      params = {
        captcha_timeout_seconds: remaining(), target_page_id: status.page_id, target_generation: status.generation,
      };
      requestAction = action;
      continue;
    }
    if (!explicit && !original && !params.captcha_id && result.action_executed !== false) {
      return failure('Server did not confirm whether the action executed', 'captcha_execution_unknown');
    }
    params.captcha_id = status.captcha_id;
    requestAction = { type: 'captcha_solve' };
    await pause(Math.min(1000, Math.max(100, status.retry_after_ms)));
  }
}
