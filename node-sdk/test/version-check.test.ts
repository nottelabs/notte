import { describe, expect, it, vi } from 'vitest';
import { checkForLatestVersion } from '@/version-check';

const createFetch = (version: string, ok = true) =>
  vi.fn(async () => ({
    ok,
    json: async () => ({ version }),
  })) as unknown as typeof fetch;

describe('version check', () => {
  it('warns when a newer npm version is available', async () => {
    const warnFn = vi.fn();

    await checkForLatestVersion({
      currentVersion: '1.2.3',
      packageName: 'notte-sdk',
      fetchFn: createFetch('1.2.4'),
      warnFn,
      env: {},
    });

    expect(warnFn).toHaveBeenCalledWith(
      '[notte-sdk] A newer version is available: 1.2.3 -> 1.2.4. Update with: npm install notte-sdk@latest'
    );
  });

  it('does not warn when the current version is latest', async () => {
    const warnFn = vi.fn();

    await checkForLatestVersion({
      currentVersion: '1.2.3',
      fetchFn: createFetch('1.2.3'),
      warnFn,
      env: {},
    });

    expect(warnFn).not.toHaveBeenCalled();
  });

  it('does not check dev, test, ci, or explicitly disabled environments', async () => {
    const cases = [
      { currentVersion: '0.0.0-dev', env: {} },
      { currentVersion: '1.2.3', env: { NODE_ENV: 'test' } },
      { currentVersion: '1.2.3', env: { VITEST: 'true' } },
      { currentVersion: '1.2.3', env: { CI: 'true' } },
      { currentVersion: '1.2.3', env: { NOTTE_SDK_DISABLE_VERSION_CHECK: '1' } },
    ];

    for (const testCase of cases) {
      const fetchFn = createFetch('9.9.9');
      const warnFn = vi.fn();

      await checkForLatestVersion({
        currentVersion: testCase.currentVersion,
        fetchFn,
        warnFn,
        env: testCase.env,
      });

      expect(fetchFn).not.toHaveBeenCalled();
      expect(warnFn).not.toHaveBeenCalled();
    }
  });

  it('stays silent when npm registry lookup fails', async () => {
    const warnFn = vi.fn();

    await checkForLatestVersion({
      currentVersion: '1.2.3',
      fetchFn: createFetch('1.2.4', false),
      warnFn,
      env: {},
    });

    expect(warnFn).not.toHaveBeenCalled();
  });
});
