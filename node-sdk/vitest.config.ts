import { defineConfig } from 'vitest/config';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  resolve: {
    alias: {
      'notte-sdk': fileURLToPath(new URL('./dist/index.mjs', import.meta.url)),
      'playwright-core': fileURLToPath(new URL('./node_modules/playwright-core/index.mjs', import.meta.url)),
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@/lib': fileURLToPath(new URL('./src/lib', import.meta.url))
    }
  },
  test: {
    // Live suites share staging quotas, not fixtures. Run files serially and
    // allow API-backed tests more than Vitest's five-second unit-test default.
    ...(process.env.VITEST_INTEGRATION ? {
      fileParallelism: false,
      testTimeout: 120000,
      hookTimeout: 60000,
    } : {}),
    globals: true,
    environment: 'node',
    include: process.env.VITEST_INTEGRATION
      ? ['test/**/*.integration.test.ts', 'test/integration.test.ts']
      : ['test/**/*.test.ts'],
    coverage: {
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'test/',
        'lib/',
        'dist/',
        '*.config.*'
      ]
    }
  },
});
