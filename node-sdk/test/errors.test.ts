import { describe, expect, it, vi } from 'vitest';
import {
  ActionExecutionError,
  AuthenticationError,
  FailedToRunCloudFunctionError,
  InvalidRequestError,
  NotteAPIError,
  NotteAPIExecutionError,
  NotteError,
  NotteTimeoutError,
  ScrapeFailedError,
  normalizeErrorBody,
  retry,
} from '@/errors';

describe('error hierarchy', () => {
  it('every SDK error extends NotteError and carries its class name', () => {
    const errors = [
      new NotteAPIError('/sessions/start', 500, { message: 'boom' }),
      new NotteAPIExecutionError('/sessions/x/page/execute', 400, { message: 'bad' }),
      new AuthenticationError('missing key'),
      new InvalidRequestError('bad arg'),
      new NotteTimeoutError('slow'),
      new FailedToRunCloudFunctionError('fn', 'run', { error: 'x' }),
      new ScrapeFailedError('no data'),
      ActionExecutionError.fromMessage('click failed'),
    ];
    for (const error of errors) {
      expect(error).toBeInstanceOf(NotteError);
      expect(error).toBeInstanceOf(Error);
      expect(error.name).toBe(error.constructor.name);
    }
  });

  it('NotteAPIError exposes path, status code and the JSON body like Python', () => {
    const error = new NotteAPIError('/sessions/start', 422, { message: 'Extra inputs are not permitted' });
    expect(error.path).toBe('/sessions/start');
    expect(error.statusCode).toBe(422);
    expect(error.error).toEqual({ message: 'Extra inputs are not permitted' });
    expect(error.apiMessage).toBe('Extra inputs are not permitted');
    expect(error.message).toBe(
      'Request to `/sessions/start` failed with status code 422: {"message":"Extra inputs are not permitted"}',
    );
  });

  it('NotteAPIError tolerates non-JSON bodies (502 html pages, empty bodies)', () => {
    expect(NotteAPIError.fromBody('/x', 502, '<html>Bad gateway</html>').error).toEqual({
      message: '<html>Bad gateway</html>',
    });
    expect(NotteAPIError.fromBody('/x', 502, '').error).toEqual({});
    expect(NotteAPIError.fromBody('/x', 502, undefined).error).toEqual({});
    expect(NotteAPIError.fromBody('/x', 502, undefined).apiMessage).toBeUndefined();
  });

  it('NotteAPIExecutionError is a NotteAPIError with the execution message format', () => {
    const error = new NotteAPIExecutionError('/sessions/x/page/execute', 400, { message: 'bad' });
    expect(error).toBeInstanceOf(NotteAPIError);
    expect(error.message).toBe('Error on /sessions/x/page/execute: {"message":"bad"}');
  });

  it('ActionExecutionError rehydrates the serialized error detail', () => {
    const error = new ActionExecutionError({
      error_type: 'ElementNotFoundError',
      dev_message: 'dev',
      user_message: 'user',
      agent_message: 'agent',
      should_retry_later: true,
    });
    expect(error.errorType).toBe('ElementNotFoundError');
    expect(error.message).toBe('dev');
    expect(error.userMessage).toBe('user');
    expect(error.agentMessage).toBe('agent');
    expect(error.shouldRetryLater).toBe(true);
    expect(error.shouldNotifyTeam).toBe(false);
  });

  it('ActionExecutionError.fromMessage mirrors the legacy string-only payload', () => {
    const error = ActionExecutionError.fromMessage('click failed');
    expect(error.errorType).toBe('NotteBaseError');
    expect(error.message).toBe('click failed');
    expect(error.userMessage).toBe('click failed');
  });

  it('normalizeErrorBody keeps objects and wraps scalars', () => {
    expect(normalizeErrorBody({ detail: 'x' })).toEqual({ detail: 'x' });
    expect(normalizeErrorBody('text')).toEqual({ message: 'text' });
    expect(normalizeErrorBody(42)).toEqual({ message: '42' });
    expect(normalizeErrorBody(null)).toEqual({});
    expect(normalizeErrorBody(['a'])).toEqual({ message: 'a' });
  });
});

describe('retry', () => {
  it('returns the first successful result', async () => {
    const fn = vi.fn().mockRejectedValueOnce(new Error('one')).mockResolvedValueOnce('ok');
    const wrapped = retry(fn, { maxTries: 3, delayMs: 0, onRetry: () => undefined });
    await expect(wrapped()).resolves.toBe('ok');
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('raises the configured message with the last error as cause after maxTries', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('always'));
    const onRetry = vi.fn();
    const wrapped = retry(fn, { maxTries: 3, delayMs: 0, errorMessage: 'gave up', onRetry });
    await expect(wrapped()).rejects.toMatchObject({ message: 'gave up', cause: expect.any(Error) });
    expect(fn).toHaveBeenCalledTimes(3);
    expect(onRetry).toHaveBeenCalledTimes(2);
  });

  it('stops early when shouldRetry returns false', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('fatal'));
    const wrapped = retry(fn, { maxTries: 5, delayMs: 0, shouldRetry: () => false });
    await expect(wrapped()).rejects.toThrow('An error occurred while executing the function');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('forwards arguments and rejects invalid maxTries', async () => {
    const fn = vi.fn(async (a: number, b: number) => a + b);
    await expect(retry(fn, { maxTries: 1 })(2, 3)).resolves.toBe(5);
    expect(() => retry(fn, { maxTries: 0 })).toThrow(InvalidRequestError);
  });
});
