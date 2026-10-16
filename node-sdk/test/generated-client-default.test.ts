import { expect, it } from 'vitest';
import { client } from '../src/lib/client/client.gen';

it('keeps the generated standalone client on production without OpenAPI servers', () => {
  expect(client.getConfig().baseUrl).toBe('https://api.notte.cc');
});
