import { expect, it, vi } from 'vitest';
import { withUsableBuiltinPage } from './helpers/builtin-page-check';

it('checks the original page and preserves its receiver and return value', async () => {
  const page = { evaluate: vi.fn().mockResolvedValue(2) };
  let calls = 0;
  const prototype = { async page() { expect(this).toBe(instance); calls++; return page; } };
  const instance = Object.create(prototype);
  const original = prototype.page;
  expect(await withUsableBuiltinPage(prototype, () => instance.page())).toBe(page);
  expect(calls).toBe(1);
  expect(page.evaluate).toHaveBeenCalledWith('1 + 1');
  expect(prototype.page).toBe(original);
});

it('rejects an unusable page and restores the original method', async () => {
  const prototype = { page: async () => ({ evaluate: async () => 3 }) };
  const original = prototype.page;
  await expect(withUsableBuiltinPage(prototype, () => prototype.page())).rejects.toThrow();
  expect(prototype.page).toBe(original);
});

it('preserves page transport errors and restores the method', async () => {
  const error = new Error('page disconnected');
  const prototype = { page: async () => ({ evaluate: async () => { throw error; } }) };
  const original = prototype.page;
  await expect(withUsableBuiltinPage(prototype, () => prototype.page())).rejects.toBe(error);
  expect(prototype.page).toBe(original);
});

it('rejects an example that does not request a page', async () => {
  const prototype = { page: async () => ({ evaluate: async () => 2 }) };
  const original = prototype.page;
  await expect(withUsableBuiltinPage(prototype, async () => undefined)).rejects.toThrow();
  expect(prototype.page).toBe(original);
});
