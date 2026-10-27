import { afterEach, expect, test } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createServer } from 'node:http';
import { createClient } from '@hey-api/openapi-ts';
import config from '../openapi-ts.config';

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'sdk-openapi-order-'));
afterEach(() => fs.rmSync(temp, { recursive: true, force: true }));

test('generation preserves declared property order for object, file and URL inputs', async () => {
  const schema = JSON.parse(fs.readFileSync(new URL('../../tests/data/openapi-order/input.json', import.meta.url), 'utf8'));
  fs.mkdirSync(temp, { recursive: true });
  const output = path.join(temp, 'client');
  const settings = { ...await config, output: { path: output } };
  async function generate(input: string | typeof schema) {
    await createClient({ ...settings, input: typeof input === 'string' ? input : structuredClone(input) });
    return Object.fromEntries(fs.readdirSync(output, { recursive: true }).map(String)
      .filter(file => fs.statSync(path.join(output, file)).isFile())
      .map(file => [file, fs.readFileSync(path.join(output, file), 'utf8')]));
  }
  const baseline = await generate(schema);
  expect(baseline['types.gen.ts'].indexOf('z: string')).toBeLessThan(baseline['types.gen.ts'].indexOf('a: number'));
  fs.mkdirSync(temp, { recursive: true });
  const file = path.join(temp, 'openapi.json');
  fs.writeFileSync(file, JSON.stringify(schema, null, 4));
  expect(await generate(file)).toEqual(baseline);
  const server = createServer((_request, response) => response.end(JSON.stringify(schema)));
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address();
    if (!address || typeof address === 'string') throw new Error('Missing local fixture port');
    expect(await generate(`http://127.0.0.1:${address.port}/openapi.json`)).toEqual(baseline);
  } finally {
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
  for (const mutate of [
    (spec: typeof schema) => { spec.components.schemas.Zebra.required.pop(); },
    (spec: typeof schema) => { spec.components.schemas.Zebra.properties.a.type = 'string'; },
    (spec: typeof schema) => { delete spec.components.schemas.Zebra.properties.z; },
    (spec: typeof schema) => { spec.components.schemas.Zebra.properties.new_field = { type: 'boolean' }; },
  ]) {
    const spec = structuredClone(schema);
    mutate(spec);
    const changed = await generate(spec);
    expect(changed).not.toEqual(baseline);
    expect(await generate(spec)).toEqual(changed);
  }
});
