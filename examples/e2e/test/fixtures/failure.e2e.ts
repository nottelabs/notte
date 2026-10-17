import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

test('deliberate assertion failure for cleanup validation', async ({ app, browser }) => {
  await app.open('/');
  await expect(browser).toHaveTitle('This title does not exist');
});
