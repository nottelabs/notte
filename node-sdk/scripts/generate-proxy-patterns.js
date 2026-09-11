#!/usr/bin/env node

/**
 * Auto-generates src/proxy/patterns.ts from the OpenAPI-generated sdk.gen.ts.
 *
 * This script reads every `url: '/...'` entry in sdk.gen.ts, deduplicates them,
 * converts path parameters like `{session_id}` into regex segments `[^/]+`,
 * and writes out a fully typed patterns.ts file.
 *
 * Run as part of `npm run generate` (after openapi-ts).
 */

const fs = require('fs');
const path = require('path');

const SERVICES_FILE = path.join(__dirname, '../src/lib/client/sdk.gen.ts');
const OUTPUT_FILE = path.join(__dirname, '../src/proxy/patterns.ts');

// Read services.gen.ts
const servicesContent = fs.readFileSync(SERVICES_FILE, 'utf8');

// Extract all unique URL patterns (e.g., "/sessions/{session_id}/stop")
const urlRegex = /url:\s*'(\/[^']*)'/g;
const urls = new Set();
let match;
while ((match = urlRegex.exec(servicesContent)) !== null) {
  urls.add(match[1]);
}

// The session-scoped file API is being released before staging's OpenAPI spec
// is updated. Keep the proxy allowlist aligned with the handwritten SessionFiles
// wrapper during that rollout; remove this compatibility block once staging
// exposes the new endpoints.
const removedDuringSessionFilesRollout = [
  '/storage/{session_id}/downloads',
  '/storage/{session_id}/downloads/{filename}',
  '/storage/uploads',
  '/storage/uploads/{filename}',
];
for (const url of removedDuringSessionFilesRollout) urls.delete(url);
urls.add('/sessions/{session_id}/files');
urls.add('/sessions/{session_id}/files/{file_id}');

// Convert URL paths to regex patterns:
//   "/sessions/{session_id}/stop"  →  "^sessions\\/[^\\/]+\\/stop$"
//   "/"                            →  "^$"
function urlToRegex(url) {
  // Strip leading slash
  const path = url.replace(/^\//, '');

  if (path === '') return '^$';

  // Replace {param} with [^/]+ and escape forward slashes
  const regexBody = path
    .split('/')
    .map(segment => {
      if (segment.startsWith('{') && segment.endsWith('}')) {
        return '[^\\/]+';
      }
      return segment;
    })
    .join('\\/');

  return `^${regexBody}$`;
}

// Group patterns by category for readability
function categorize(url) {
  const path = url.replace(/^\//, '');
  if (path === '' || path === 'health' || path === 'scrape' || path === 'scrape_from_html') return 'Root';
  const prefix = path.split('/')[0];
  return prefix.charAt(0).toUpperCase() + prefix.slice(1);
}

// Sort URLs, deduplicate, and group
const sortedUrls = [...urls].sort((a, b) => {
  const catA = categorize(a);
  const catB = categorize(b);
  if (catA !== catB) return catA.localeCompare(catB);
  return a.localeCompare(b);
});

const groups = new Map();
for (const url of sortedUrls) {
  const cat = categorize(url);
  if (!groups.has(cat)) groups.set(cat, []);
  groups.get(cat).push(url);
}

// Generate the output file content
const lines = [];
lines.push(`/**`);
lines.push(` * Auto-generated from sdk.gen.ts by scripts/generate-proxy-patterns.js`);
lines.push(` * DO NOT EDIT MANUALLY — re-run \`npm run generate\` to update.`);
lines.push(` *`);
lines.push(` * Allowed API endpoint patterns to prevent SSRF attacks.`);
lines.push(` * Every pattern corresponds to an endpoint in the Notte API OpenAPI spec.`);
lines.push(` */`);
lines.push(`export const DEFAULT_ALLOWED_PATTERNS: RegExp[] = [`);

let firstGroup = true;
for (const [category, categoryUrls] of groups) {
  if (!firstGroup) lines.push('');
  firstGroup = false;
  lines.push(`  // ${category} endpoints`);
  for (const url of categoryUrls) {
    const regex = urlToRegex(url);
    const comment = url;
    lines.push(`  /${regex}/, // ${comment}`);
  }
}

lines.push(`];`);
lines.push('');
lines.push(`export interface PathValidationResult {`);
lines.push(`  isValid: boolean;`);
lines.push(`  error?: string;`);
lines.push(`}`);
lines.push('');
lines.push(`/**`);
lines.push(` * Validates a request path against a list of allowed patterns.`);
lines.push(` * Prevents directory traversal and SSRF attacks.`);
lines.push(` */`);
lines.push(`export function validatePath(`);
lines.push(`  pathSegments: string[],`);
lines.push(`  allowedPatterns: RegExp[],`);
lines.push(`): PathValidationResult {`);
lines.push(`  const path = pathSegments.join('/');`);
lines.push('');
lines.push(`  // Check for directory traversal attempts`);
lines.push(`  if (path.includes('..') || path.includes('//') || path.startsWith('/')) {`);
lines.push(`    return {`);
lines.push(`      isValid: false,`);
lines.push(`      error: 'Invalid path: directory traversal detected',`);
lines.push(`    };`);
lines.push(`  }`);
lines.push('');
lines.push(`  // Check against allowed patterns`);
lines.push(`  const isValidPattern = allowedPatterns.some((pattern) => pattern.test(path));`);
lines.push(`  if (!isValidPattern) {`);
lines.push(`    return {`);
lines.push(`      isValid: false,`);
lines.push(`      error: \`Invalid path: \${path} does not match any allowed endpoint pattern\`,`);
lines.push(`    };`);
lines.push(`  }`);
lines.push('');
lines.push(`  return { isValid: true };`);
lines.push(`}`);
lines.push('');

fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
fs.writeFileSync(OUTPUT_FILE, lines.join('\n'), 'utf8');

console.log(`Generated ${OUTPUT_FILE} with ${sortedUrls.length} unique URL patterns from ${urls.size} total entries`);
