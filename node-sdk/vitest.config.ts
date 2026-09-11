import { defineConfig } from 'vitest/config';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@/lib': fileURLToPath(new URL('./src/lib', import.meta.url))
    }
  },
  test: {
    globals: true,
    environment: 'node',
    include: process.env.VITEST_INTEGRATION
      ? ['test/**/*.integration.test.ts']
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
