import { afterEach, expect, it, vi } from 'vitest';

const fixture = vi.hoisted(() => ({ listedStatus: 'failed', requested: false, inspected: [] as string[] }));
vi.mock('notte-sdk', () => ({
  NotteClient: class {
    NotteFunction() {
      return {
        async run() { return { function_run_id: 'owned-run', status: 'failed' }; },
        async runs(options: { only_active: boolean }) {
          fixture.requested = options.only_active === false;
          return { items: [{ function_run_id: 'owned-run', status: fixture.listedStatus, created_at: 'now' }] };
        },
        async getRun(id: string) {
          fixture.inspected.push(id);
          return { result: 'Example function failure' };
        },
      };
    }
  },
}));

afterEach(() => vi.restoreAllMocks());

it.each(['failed', 'closed'])('failed-run example rejects incorrect listed status: %s', async listedStatus => {
  vi.resetModules();
  Object.assign(fixture, { listedStatus, requested: false, inspected: [] });
  vi.spyOn(console, 'log').mockImplementation(() => {});
  const name = 'high_failure_rate';
  const execution = import(`../../docs/src/testers/functions/management/${name}.ts`);
  if (listedStatus === 'failed') {
    await expect(execution).resolves.toMatchObject({ results: ['failed', true] });
    expect(fixture.inspected).toEqual(['owned-run', 'owned-run']);
  } else {
    await expect(execution).rejects.toThrow('Seeded failed run owned-run; listed owned-run:closed');
  }
  expect(fixture.requested).toBe(true);
});
