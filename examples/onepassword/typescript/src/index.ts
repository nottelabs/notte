import { runDemo } from './demo.ts';

try {
  console.log(JSON.stringify(await runDemo()));
} catch (error) {
  console.error(error instanceof Error ? error.message : 'Vault form failed');
  process.exitCode = 1;
}
