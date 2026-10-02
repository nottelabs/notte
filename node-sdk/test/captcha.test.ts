import { afterEach, describe, expect, it, vi } from 'vitest';
import { createServer } from 'node:http';
import { NotteClient } from '@/client';
import { executeWithCaptcha, type CaptchaExecutionResponse, type CaptchaStatus } from '@/captcha';
import { NotteAPIError, NotteTimeoutError } from '@/errors';
import type { ExecuteAction } from '@/actions';
import { executionResult, sessionResponse } from './helpers/session-mocks';

vi.mock('@/version-check', () => ({ startVersionCheck: vi.fn(), upgradeSuggestion: vi.fn() }));
const action: ExecuteAction = { type: 'click', selector: '#submit' };
function response(state: CaptchaStatus['state'], executed: boolean | null = false): CaptchaExecutionResponse {
  return { ...executionResult(), success: state === 'solved', action_executed: executed,
    captcha: { captcha_id: 'c', page_id: 'p', generation: 3, state, retry_after_ms: 100 } };
}
afterEach(() => vi.useRealTimers());

describe('CAPTCHA polling', () => {
  it('uses the default polling delay when the optional retry hint is absent', async () => {
    vi.useFakeTimers();
    const pending = response('solving');
    delete pending.captcha!.retry_after_ms;
    const request = vi.fn().mockResolvedValueOnce(pending).mockResolvedValueOnce(response('solved'));
    const result = executeWithCaptcha({ type: 'captcha_solve' }, 180, request);
    await vi.advanceTimersByTimeAsync(999);
    expect(request).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect((await result).success).toBe(true);
    expect(request).toHaveBeenCalledTimes(2);
  });
  it('resubmits a blocked action only after solved and with page guards', async () => {
    const request = vi.fn().mockResolvedValueOnce(response('solving'))
      .mockResolvedValueOnce(response('solved')).mockResolvedValueOnce(executionResult());
    expect((await executeWithCaptcha(action, 180, request)).success).toBe(true);
    expect(request.mock.calls.map(c => c[0].type)).toEqual(['click', 'captcha_solve', 'click']);
    expect(request.mock.calls[2][1]).toMatchObject({ target_page_id: 'p', target_generation: 3 });
    expect(request.mock.calls[2][1].captcha_id).toBeUndefined();
  });
  it('preserves an already executed action instead of repeating it', async () => {
    const original = { ...response('solving', true), success: true, data: { value: 42 } };
    const request = vi.fn().mockResolvedValueOnce(original).mockResolvedValueOnce(response('solved'));
    expect(await executeWithCaptcha(action, 180, request)).toMatchObject({ data: { value: 42 }, success: true });
    expect(request).toHaveBeenCalledTimes(2);
  });
  it.each(['failed', 'cancelled'] as const)('does not replay after %s', async state => {
    const request = vi.fn().mockResolvedValueOnce(response('solving')).mockResolvedValue(response(state));
    expect(await executeWithCaptcha(action, 180, request)).toMatchObject({ success: false, code: `captcha_${state}` });
    expect(request).toHaveBeenCalledTimes(2);
  });
  it('fails closed if the server does not report execution state', async () => {
    const request = vi.fn().mockResolvedValue(response('solving', null));
    expect(await executeWithCaptcha(action, 180, request)).toMatchObject({ code: 'captcha_execution_unknown' });
    expect(request).toHaveBeenCalledTimes(1);
  });
  it.each(['missing', 'different'])('rejects %s polling identity', async mode => {
    const next = mode === 'missing' ? executionResult() : { ...response('solved'), captcha: { ...response('solved').captcha!, captcha_id: 'other' } };
    const request = vi.fn().mockResolvedValueOnce(response('solving')).mockResolvedValueOnce(next);
    expect(await executeWithCaptcha(action, 180, request)).toMatchObject({ code: 'captcha_protocol_error' });
    expect(request).toHaveBeenCalledTimes(2);
  });
  it('recovers only polling transport errors and retains the solve ID', async () => {
    const request = vi.fn().mockResolvedValueOnce(response('solving'))
      .mockRejectedValueOnce(new NotteTimeoutError('timeout'))
      .mockRejectedValueOnce(new TypeError('connection reset'))
      .mockRejectedValueOnce(new NotteAPIError('/execute', 503, {}))
      .mockResolvedValueOnce(response('solved'));
    vi.useFakeTimers();
    const result = executeWithCaptcha({ type: 'captcha_solve' }, 180, request);
    await vi.runAllTimersAsync();
    expect((await result).success).toBe(true);
    expect(request.mock.calls.slice(1).every(c => c[1].captcha_id === 'c')).toBe(true);
  });
  it('does not resend an initial explicit solve after losing its response', async () => {
    const request = vi.fn().mockRejectedValue(new NotteTimeoutError('initial response lost'));
    await expect(executeWithCaptcha({ type: 'captcha_solve' }, 180, request)).rejects.toThrow('initial response lost');
    expect(request).toHaveBeenCalledTimes(1);
  });
  it('does not retry ambiguous transport failures of ordinary actions', async () => {
    const request = vi.fn().mockRejectedValue(new NotteTimeoutError('timeout'));
    await expect(executeWithCaptcha(action, 180, request)).rejects.toThrow('timeout');
    expect(request).toHaveBeenCalledTimes(1);
  });
  it('waits longer than 60 seconds using short requests and stops at its budget', async () => {
    vi.useFakeTimers();
    const request = vi.fn().mockResolvedValue(response('solving'));
    const result = executeWithCaptcha({ type: 'captcha_solve' }, 75, request);
    await vi.advanceTimersByTimeAsync(61000);
    expect(request.mock.calls.length).toBeGreaterThan(60);
    expect(request.mock.calls.every(c => c[2] <= 10000)).toBe(true);
    await vi.advanceTimersByTimeAsync(15000);
    expect(await result).toMatchObject({ code: 'captcha_timeout' });
  });
  it.each([0, -1, Infinity, NaN])('rejects invalid budget %s', value => {
    expect(() => new NotteClient({ apiKey: 'test', captchaTimeoutSeconds: value })).toThrow('positive and finite'); // pragma: allowlist secret - dummy test credential
  });
  it('carries the polling protocol through the real client and HTTP transport', async () => {
    const received: { body: ExecuteAction; url: URL }[] = [];
    const server = createServer(async (req, res) => {
      res.setHeader('Content-Type', 'application/json');
      if (!req.url?.includes('/page/execute')) { res.end(JSON.stringify(sessionResponse())); return; }
      let raw = ''; for await (const chunk of req) raw += chunk;
      received.push({ body: JSON.parse(raw), url: new URL(req.url, 'http://localhost') });
      res.end(JSON.stringify(received.length === 1 ? response('solving') : received.length === 2 ? response('solved') : executionResult()));
    });
    await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
    try {
      const address = server.address() as { port: number };
      const client = new NotteClient({ apiKey: 'test', baseUrl: `http://127.0.0.1:${address.port}`, captchaTimeoutSeconds: 30 }); // pragma: allowlist secret - local test credential
      const session = client.Session(); await session.start();
      expect((await session.execute(action)).success).toBe(true);
      expect(received.map(r => r.body.type)).toEqual(['click', 'captcha_solve', 'click']);
      expect(received[1].url.searchParams.get('captcha_id')).toBe('c');
      expect(received[2].url.searchParams.get('target_generation')).toBe('3');
      expect(received[2].url.searchParams.get('target_page_id')).toBe('p');
    } finally { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); }
  });
});

describe('navigation during post-action CAPTCHA waiting', () => {
  it.each([true, false])('preserves the executed result (success=%s) without replay', async success => {
    const original = { ...response('solving', true), success, data: { value: 42 } };
    const cancelled = response('cancelled');
    cancelled.captcha!.cancel_reason = 'navigation';
    const request = vi.fn().mockResolvedValueOnce(original).mockResolvedValueOnce(cancelled);
    expect(await executeWithCaptcha(action, 180, request)).toMatchObject({
      success, data: { value: 42 }, action_executed: true,
      captcha: { state: 'cancelled', cancel_reason: 'navigation' },
    });
    expect(request).toHaveBeenCalledTimes(2);
  });
  it.each([undefined, null, 'unknown'])('fails an executed cancellation with reason %s', async reason => {
    const original = { ...response('solving', true), success: true };
    const cancelled = response('cancelled');
    // Simulate an unexpected server value without widening the generated API contract.
    Object.assign(cancelled.captcha!, { cancel_reason: reason });
    const request = vi.fn().mockResolvedValueOnce(original).mockResolvedValueOnce(cancelled);
    expect(await executeWithCaptcha(action, 180, request)).toMatchObject({
      success: false, action_executed: true, code: 'captcha_cancelled',
    });
    expect(request.mock.calls.map(call => call[0].type)).toEqual(['click', 'captcha_solve']);
    expect(request).toHaveBeenCalledTimes(2);
  });
  it.each([action, { type: 'captcha_solve' } as ExecuteAction])('still fails an unexecuted $type', async input => {
    const cancelled = response('cancelled');
    cancelled.captcha!.cancel_reason = 'navigation';
    const request = vi.fn().mockResolvedValueOnce(response('solving')).mockResolvedValueOnce(cancelled);
    expect(await executeWithCaptcha(input, 180, request)).toMatchObject({ success: false, code: 'captcha_cancelled' });
    expect(request).toHaveBeenCalledTimes(2);
  });
});

it('returns an executed goto through Session.execute after a navigation cancellation', async () => {
  const received: ExecuteAction[] = [];
  const goto: ExecuteAction = { type: 'goto', url: 'https://fixture.test/' };
  const server = createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    if (!req.url?.includes('/page/execute')) { res.end(JSON.stringify(sessionResponse())); return; }
    let raw = ''; for await (const chunk of req) raw += chunk;
    received.push(JSON.parse(raw));
    const result = received.length === 1
      ? { ...response('solving', true), action: goto, success: true }
      : response('cancelled');
    if (received.length > 1) result.captcha!.cancel_reason = 'navigation';
    res.end(JSON.stringify(result));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address() as { port: number };
    const client = new NotteClient({ apiKey: 'test', baseUrl: `http://127.0.0.1:${address.port}` }); // pragma: allowlist secret - local fixture
    const session = client.Session(); await session.start();
    const result = await session.execute(goto);
    expect(result.success).toBe(true);
    expect(result.action).toMatchObject(goto);
    expect(received.map(input => input.type)).toEqual(['goto', 'captcha_solve']);
  } finally { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); }
});

describe('navigation before a wait executes', () => {
  const wait: ExecuteAction = { type: 'wait', time_ms: 5000 };
  const navigation = () => {
    const result = response('cancelled');
    result.captcha!.cancel_reason = 'navigation';
    return result;
  };
  it('checks the new page and resumes the wait after its challenge', async () => {
    const next = response('solving');
    Object.assign(next.captcha!, { captcha_id: 'next', generation: 4 });
    const solved = { ...response('solved'), captcha: { ...next.captcha!, state: 'solved' as const } };
    const request = vi.fn().mockResolvedValueOnce(response('solving')).mockResolvedValueOnce(navigation())
      .mockResolvedValueOnce(next).mockResolvedValueOnce(solved)
      .mockResolvedValueOnce({ ...executionResult(), action: wait, action_executed: true });
    expect(await executeWithCaptcha(wait, 180, request)).toMatchObject({ success: true, action_executed: true });
    expect(request.mock.calls.map(c => c[0].type)).toEqual(['wait', 'captcha_solve', 'wait', 'captcha_solve', 'wait']);
    expect(request.mock.calls[2][1].captcha_id).toBeUndefined();
    expect(request.mock.calls[2][1].target_generation).toBeUndefined();
    expect(request.mock.calls[3][1].captcha_id).toBe('next');
    expect(request.mock.calls[4][1].target_generation).toBe(4);
    expect(request.mock.calls[2][1].captcha_timeout_seconds).toBeLessThan(180);
  });
  it('bounds repeated navigation by the original deadline', async () => {
    vi.useFakeTimers();
    const request = vi.fn().mockResolvedValue(navigation());
    const pending = executeWithCaptcha(wait, 3, request);
    await vi.advanceTimersByTimeAsync(3000);
    expect(await pending).toMatchObject({ success: false, code: 'captcha_timeout' });
    expect(request).toHaveBeenCalledTimes(3);
  });
  it('keeps the requested wait duration separate from the CAPTCHA budget', async () => {
    vi.useFakeTimers();
    const request = vi.fn().mockResolvedValueOnce(navigation()).mockImplementationOnce(async () => {
      await new Promise(resolve => setTimeout(resolve, wait.time_ms));
      return { ...executionResult(), action: wait, action_executed: true };
    });
    const pending = executeWithCaptcha(wait, 2, request);
    await vi.advanceTimersByTimeAsync(6000);
    expect(await pending).toMatchObject({ success: true, action: wait, action_executed: true });
    expect(request).toHaveBeenCalledTimes(2);
    expect(request.mock.calls[1]).toEqual([wait, { captcha_timeout_seconds: 1 }, undefined]);
  });
  it.each(['failed', 'cancelled'] as const)('does not hide other %s outcomes', async state => {
    const request = vi.fn().mockResolvedValue(response(state));
    expect(await executeWithCaptcha(wait, 180, request)).toMatchObject({ success: false, code: `captcha_${state}` });
    expect(request).toHaveBeenCalledTimes(1);
  });
  it('does not repeat an already executed wait', async () => {
    const request = vi.fn().mockResolvedValueOnce({ ...response('solving', true), success: true })
      .mockResolvedValueOnce(navigation());
    expect(await executeWithCaptcha(wait, 180, request)).toMatchObject({ success: true, action_executed: true });
    expect(request).toHaveBeenCalledTimes(2);
  });
  it.each(['poll', 'guarded retry'])('recovers through Session.execute and HTTP after navigation during %s', async phase => {
    const next = response('solving');
    Object.assign(next.captcha!, { captcha_id: 'next', page_id: 'destination', generation: 4 });
    const responses = [
      response('solving'),
      ...(phase === 'guarded retry' ? [response('solved')] : []),
      navigation(),
      next,
      { ...response('solved'), captcha: { ...next.captcha!, state: 'solved' as const } },
      { ...executionResult(), action: wait, action_executed: true },
    ];
    const received: { body: ExecuteAction; url: URL }[] = [];
    const server = createServer(async (req, res) => {
      res.setHeader('Content-Type', 'application/json');
      if (!req.url?.includes('/page/execute')) { res.end(JSON.stringify(sessionResponse())); return; }
      let raw = ''; for await (const chunk of req) raw += chunk;
      const body: ExecuteAction = JSON.parse(raw);
      const result = responses[received.length];
      received.push({ body, url: new URL(req.url, 'http://localhost') });
      if (!result) { res.writeHead(500); res.end('{}'); return; }
      res.end(JSON.stringify({ ...result, action: body }));
    });
    await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
    try {
      const address = server.address() as { port: number };
      const client = new NotteClient({ apiKey: 'test', baseUrl: `http://127.0.0.1:${address.port}`, captchaTimeoutSeconds: 30 }); // pragma: allowlist secret - local fixture
      const session = client.Session(); await session.start();
      expect(await session.execute(wait)).toMatchObject({ success: true, action: wait, action_executed: true });
      expect(received.map(r => r.body.type)).toEqual([
        'wait', 'captcha_solve', ...(phase === 'guarded retry' ? ['wait'] : []),
        'wait', 'captcha_solve', 'wait',
      ]);
      expect(received[1].url.searchParams.get('captcha_id')).toBe('c');
      if (phase === 'guarded retry') {
        expect(received[2].url.searchParams.get('target_page_id')).toBe('p');
        expect(received[2].url.searchParams.get('target_generation')).toBe('3');
      }
      const [retry, poll, resumed] = received.slice(-3);
      expect(retry.body).toEqual(wait);
      expect([...retry.url.searchParams.keys()]).toEqual(['captcha_timeout_seconds']);
      expect(poll.url.searchParams.get('captcha_id')).toBe('next');
      expect(resumed.body).toEqual(wait);
      expect(resumed.url.searchParams.get('captcha_id')).toBeNull();
      expect(resumed.url.searchParams.get('target_page_id')).toBe('destination');
      expect(resumed.url.searchParams.get('target_generation')).toBe('4');
      const budgets = received.map(r => Number(r.url.searchParams.get('captcha_timeout_seconds')));
      expect(budgets.every((budget, i) => budget > 0 && (i === 0 || budget < budgets[i - 1]))).toBe(true);
    } finally { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); }
  });
});
