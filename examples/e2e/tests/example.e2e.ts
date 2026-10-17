import { test } from '@e2e-dev/web';
import { expect } from 'e2e';

test('the example page links to IANA', async ({ app, screen }) => {
  await app.open('/');
  await expect(screen.getByRole('link', 'Learn more')).toBeVisible();
});
