import { afterEach, expect, it, vi } from 'vitest';

// Every page holds 100 functions; the first unpaged call returns the first 20.
const fixture = vi.hoisted(() => ({ ownedPage: 0 as number | null, totalPages: 3, calls: [] as unknown[] }));
vi.mock('notte-sdk', () => {
  const fn = (id: string) => ({ function_id: id, name: id, versions: ['v1'], latest_version: 'v1' });
  const page = (number: number) => Array.from({ length: number < fixture.totalPages ? 100 : 40 }, (_, i) =>
    fn(number === fixture.ownedPage && i === 7 ? 'owned' : `other-${number}-${i}`));
  return {
    NotteClient: class {
      functions = {
        async list(query?: { page: number; page_size: number }) {
          fixture.calls.push(query);
          if (!query) return fixture.ownedPage === 0 ? [fn('owned')] : page(1).slice(0, 20).filter(f => f.function_id !== 'owned');
          return query.page <= fixture.totalPages ? page(query.page) : [];
        },
      };
    },
  };
});

afterEach(() => vi.restoreAllMocks());

it.each([1, 3])('finds the owned function on page %i', async ownedPage => {
  vi.resetModules();
  Object.assign(fixture, { ownedPage, calls: [] });
  vi.stubEnv('NOTTE_FUNCTION_ID', 'owned');
  vi.spyOn(console, 'log').mockImplementation(() => {});
  await expect(import('../../docs/src/testers/functions/management/version_history.ts')).resolves.toMatchObject({ results: [true, true] });
  expect(fixture.calls).toContainEqual({ page: ownedPage, page_size: 100 });
});

it('fails when the owned function is on no page', async () => {
  vi.resetModules();
  Object.assign(fixture, { ownedPage: null, calls: [] });
  vi.stubEnv('NOTTE_FUNCTION_ID', 'owned');
  vi.spyOn(console, 'log').mockImplementation(() => {});
  await expect(import('../../docs/src/testers/functions/management/version_history.ts')).rejects.toThrow('Owned function missing from history');
  // Stops at the last, short page instead of paging forever.
  expect(fixture.calls.at(-1)).toEqual({ page: fixture.totalPages, page_size: 100 });
});
