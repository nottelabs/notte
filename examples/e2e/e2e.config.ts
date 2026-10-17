import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';
import { notte } from './src/notte.ts';

export default {
  targets: [{ name: 'notte', engine: web({ browser: notte() }), app: { url: 'https://example.com' } }],
  workers: 1,
  retries: 0,
  secrets: { notteApiKey: () => process.env.NOTTE_API_KEY ?? '' },
} satisfies E2EConfig;
