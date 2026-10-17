import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';

for (const rejected of [false, true]) {
  test(rejected ? 'registration failure never starts an agent' : 'gateway registration preserves the secret placeholder and keeps keys out of argv', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'notte-sbx-contract-'));
    try {
      const record = join(directory, 'calls.jsonl');
      const fake = `#!/usr/bin/env node\nconst fs=require('node:fs');fs.appendFileSync(process.env.TEST_CALLS,JSON.stringify(process.argv.slice(2))+'\\n');if(process.env.TEST_REJECT==='1'&&process.argv[2]==='mcp')process.exit(9);\n`;
      await writeFile(join(directory, 'sbx'), fake, { mode: 0o700 });
      const result = spawnSync('sh', ['setup.sh', 'claude', 'isolated-test'], {
        env: { ...process.env, PATH: `${directory}:${process.env.PATH}`, TEST_CALLS: record, TEST_REJECT: rejected ? '1' : '0', NOTTE_API_KEY: 'test-only-never-in-argv' }, encoding: 'utf8',
      });
      const logged = await readFile(record, 'utf8');
      const calls = logged.trim().split('\n').map(line => JSON.parse(line));
      assert.ok(!`${logged}${result.stdout}${result.stderr}`.includes('test-only-never-in-argv'));
      assert.deepEqual(calls[0], ['mcp', 'add', 'notte', '--url', 'https://api.notte.cc/mcp', '--header', 'Authorization: Bearer ${api-key}']);
      assert.equal(result.status, rejected ? 9 : 0);
      if (rejected) assert.equal(calls.length, 1);
      else {
        assert.deepEqual(calls[1], ['secret', 'set', 'mcp:notte:api-key']);
        assert.deepEqual(calls[2], ['run', 'claude', '--name', 'isolated-test', '--static-mcp', 'notte']);
      }
    } finally { await rm(directory, { recursive: true, force: true }); }
  });
}
