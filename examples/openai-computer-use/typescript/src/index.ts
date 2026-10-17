import { runDemo } from './demo.ts';

try { console.log(JSON.stringify(await runDemo())); }
catch (error) { console.error(error instanceof Error ? error.message : 'Computer use failed'); process.exitCode = 1; }
