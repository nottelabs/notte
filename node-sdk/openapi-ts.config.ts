import { defineConfig } from '@hey-api/openapi-ts';
import { createHash } from 'node:crypto';
import { orderOpenApi } from './scripts/openapi-order.js';

let schemaDigest = '';

export default defineConfig({
    input: '../openapi/openapi.json',
    parser: { patch: { input: (spec) => {
        orderOpenApi(spec);
        schemaDigest = createHash('sha256').update(JSON.stringify(spec)).digest('hex');
    } } },
    output: {
        path: 'src/lib/client',
        // Preserve drift detection for constraints/defaults absent from TS types.
        header: ({ file, defaultValue }) => file?.name === 'types.gen'
            ? [...defaultValue, `// Normalized OpenAPI SHA256: ${schemaDigest}`]
            : defaultValue,
    },
    plugins: [
        '@hey-api/typescript',
        '@hey-api/sdk',
        // The committed snapshot has no servers; preserve the runtime default.
        { name: '@hey-api/client-fetch', baseUrl: 'https://api.notte.cc' },
    ],
});
