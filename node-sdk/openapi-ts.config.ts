import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
    input: '../openapi/openapi.json',
    output: 'src/lib/client',
    plugins: [
        '@hey-api/typescript',
        '@hey-api/sdk',
        // The committed snapshot has no servers; preserve the runtime default.
        { name: '@hey-api/client-fetch', baseUrl: 'https://api.notte.cc' },
    ],
});
