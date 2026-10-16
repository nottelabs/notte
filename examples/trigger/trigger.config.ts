import { defineConfig } from '@trigger.dev/sdk';

const project = process.env.TRIGGER_PROJECT_REF;
if (!project) throw new Error('Set TRIGGER_PROJECT_REF');

export default defineConfig({
  project,
  runtime: 'node-24',
  dirs: ['./src/trigger'],
  maxDuration: 120,
  retries: { enabledInDev: true },
});
