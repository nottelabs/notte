import { runDemo } from './demo.ts';

try {
  console.log(JSON.stringify(await runDemo(process.argv[2])));
} catch (error) {
  console.error(error instanceof Error ? error.message : 'Browser tracing failed');
  process.exitCode = 1;
}
