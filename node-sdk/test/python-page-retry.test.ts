import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { withPythonPageRetry } from './helpers/python-page-retry';

const example = 'sessions/configuration/timeout.ts';
const traceback = 'Traceback (most recent call last):\n  page.goto("https://example.com")\nplaywright._impl._errors.TargetClosedError: Page.goto: Target page, context or browser has been closed\nCall log:\n  - navigating to "https://example.com/", waiting until "load"\n';
const browserLost = Object.assign(new Error('Python failed'), { stderr: traceback });

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('returns a successful execution without waiting', async () => {
  const run = vi.fn().mockResolvedValue({ stdout: 'result' });
  await expect(withPythonPageRetry(example, run)).resolves.toEqual({ stdout: 'result' });
  expect(run).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it('reruns the Python process exactly once after five seconds', async () => {
  const run = vi.fn().mockRejectedValueOnce(browserLost).mockResolvedValueOnce({ stdout: 'fresh result' });
  const result = withPythonPageRetry(example, run);
  await vi.advanceTimersByTimeAsync(4999);
  expect(run).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  await expect(result).resolves.toEqual({ stdout: 'fresh result' });
  expect(run).toHaveBeenCalledTimes(2);
  expect(console.warn).toHaveBeenCalledWith(expect.stringContaining('retrying once'));
});

it('surfaces the second failure', async () => {
  const run = vi.fn().mockRejectedValue(browserLost);
  const result = expect(withPythonPageRetry(example, run)).rejects.toBe(browserLost);
  await vi.advanceTimersByTimeAsync(5000);
  await result;
  expect(run).toHaveBeenCalledTimes(2);
});

it.each([
  ['sessions/lifecycle/create_session.ts', browserLost],
  [example, new Error('Python timed out')],
  [example, Object.assign(new Error('Python failed'), { stderr: 'RuntimeError: authentication failed' })],
  [example, Object.assign(new Error('cleanup failed'), {
    stderr: `${traceback}\nDuring handling of the above exception, another exception occurred:\n\nTraceback (most recent call last):\n  session.stop()\nRuntimeError: failed to stop`,
  })],
])('does not retry unrelated failures or failed cleanup (%s)', async (name, error) => {
  const run = vi.fn().mockRejectedValue(error);
  await expect(withPythonPageRetry(name, run)).rejects.toBe(error);
  expect(run).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});
