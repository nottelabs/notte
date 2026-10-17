import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';

const executable = process.argv[2] ?? 'sbx';
for (const [args, flags] of [
  [['mcp', 'add'], ['--url', '--header']],
  [['secret', 'set'], []],
  [['run'], ['--name', '--static-mcp']],
]) {
  const result = spawnSync(executable, [...args, '--help'], { encoding: 'utf8' });
  assert.equal(result.status, 0, `Native sbx ${args.join(' ')} contract unavailable`);
  for (const flag of flags) assert.ok(result.stdout.includes(flag), `Native sbx does not support ${flag}`);
}
console.log('Native Docker Sandboxes CLI contracts verified; no sandbox or credentials created');
