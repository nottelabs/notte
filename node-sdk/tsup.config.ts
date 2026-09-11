import { defineConfig } from 'tsup';
import pkg from './package.json';

export default defineConfig({
  entry: ['src/index.ts', 'src/proxy/next.ts', 'src/proxy/core.ts'],
  format: ['cjs', 'esm'],
  dts: true,
  clean: true,
  sourcemap: true,
  splitting: false,
  tsconfig: './tsconfig.json',
  define: {
    __SDK_VERSION__: JSON.stringify(pkg.version),
    __SDK_PACKAGE_NAME__: JSON.stringify(pkg.name),
  },
  external: ['next', 'next/server'],
});
