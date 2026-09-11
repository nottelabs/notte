#!/usr/bin/env node

/**
 * Normalizes generated files to ensure consistent formatting
 * - Converts all line endings to LF
 * - Ensures files end with a single newline
 * - Removes trailing whitespace
 */

const fs = require('fs');
const path = require('path');

const GENERATED_DIR = path.join(__dirname, '../src/lib/client');
const GENERATED_FILES = [
	'index.ts',
	'client.gen.ts',
	'sdk.gen.ts',
	'types.gen.ts',
];

const DETECT_SECRETS_ALLOWLIST = '// pragma: allowlist secret'; // pragma: allowlist secret
const SECRET_NAMESPACE_TYPE_PATTERN = /^export type SecretNamespace = .*;(?: \/\/ pragma: allowlist secret)?$/m; // pragma: allowlist secret

function normalizeFile(filePath) {
	let content = fs.readFileSync(filePath, 'utf8');

	// Remove trailing whitespace from each line
	content = content.split('\n').map(line => line.replace(/\s+$/, '')).join('\n');

	// Normalize line endings to LF (remove any CRLF)
	content = content.replace(/\r\n/g, '\n');
	content = content.replace(/\r/g, '\n');

	// OpenAPI includes illustrative proxy credentials, not actual secrets.
	content = content.replace(/^(\s*\* `https?:\/\/user:pass@host:\d+`[^\n]*?)\s*(?:\/\/ pragma: allowlist secret)?$/gm,
		(_, example) => `${example} ${DETECT_SECRETS_ALLOWLIST}`); // pragma: allowlist secret

	// Ensure file ends with exactly one newline
	content = content.replace(/\n+$/, '') + '\n';

	// detect-secrets scans staged generated files and flags this schema type name.
	if (path.basename(filePath) === 'types.gen.ts' && SECRET_NAMESPACE_TYPE_PATTERN.test(content)) {
		content = content.replace(SECRET_NAMESPACE_TYPE_PATTERN, line => {
			return line.includes(DETECT_SECRETS_ALLOWLIST) ? line : `${line} ${DETECT_SECRETS_ALLOWLIST}`;
		});

		if (!SECRET_NAMESPACE_TYPE_PATTERN.test(content) || !content.includes(DETECT_SECRETS_ALLOWLIST)) {
			throw new Error(`Failed to apply detect-secrets allowlist to ${filePath}`);
		}
	}

	fs.writeFileSync(filePath, content, 'utf8');
}

// Normalize all generated files
GENERATED_FILES.forEach(file => {
	const filePath = path.join(GENERATED_DIR, file);
	if (fs.existsSync(filePath)) {
		normalizeFile(filePath);
		console.log(`Normalized: ${file}`);
	} else {
		console.warn(`Warning: ${file} not found`);
	}
});

console.log('✅ All generated files normalized');
