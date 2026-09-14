import { expect, vi } from 'vitest';

interface PageProvider {
  page(): Promise<{ evaluate(expression: string): Promise<unknown> }>;
}

/** Check the real page before session.use() closes it, without displaying test code. */
export async function withUsableBuiltinPage<T>(prototype: PageProvider, run: () => Promise<T>): Promise<T> {
  const original = prototype.page;
  const page = vi.spyOn(prototype, 'page').mockImplementation(async function (this: PageProvider) {
    // Keep the actual SDK connection and returned Playwright page unmodified.
    const result = await original.call(this);
    expect(await result.evaluate('1 + 1')).toBe(2);
    return result;
  });
  try {
    const result = await run();
    expect(page).toHaveBeenCalledTimes(1);
    return result;
  } finally {
    page.mockRestore();
  }
}
