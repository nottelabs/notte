import { defineConfig } from '@hey-api/openapi-ts';
import dotenv from 'dotenv';
dotenv.config();

const baseUrl = process.env.NOTTE_API_URL || 'https://us-staging.notte.cc';

export default defineConfig({
    input: `${baseUrl}/openapi.json`,
    output: 'src/lib/client',
    client: '@hey-api/client-fetch',
});
