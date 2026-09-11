/**
 * Auto-generated from sdk.gen.ts by scripts/generate-proxy-patterns.js
 * DO NOT EDIT MANUALLY — re-run `npm run generate` to update.
 *
 * Allowed API endpoint patterns to prevent SSRF attacks.
 * Every pattern corresponds to an endpoint in the Notte API OpenAPI spec.
 */
export const DEFAULT_ALLOWED_PATTERNS: RegExp[] = [
  // Agents endpoints
  /^agents$/, // /agents
  /^agents\/[^\/]+$/, // /agents/{agent_id}
  /^agents\/[^\/]+\/stop$/, // /agents/{agent_id}/stop
  /^agents\/[^\/]+\/workflow\/code$/, // /agents/{agent_id}/workflow/code
  /^agents\/start$/, // /agents/start

  // Anything endpoints
  /^anything\/start$/, // /anything/start

  // Functions endpoints
  /^functions$/, // /functions
  /^functions\/[^\/]+$/, // /functions/{function_id}
  /^functions\/[^\/]+\/fork$/, // /functions/{function_id}/fork
  /^functions\/[^\/]+\/rollback$/, // /functions/{function_id}/rollback
  /^functions\/[^\/]+\/runs$/, // /functions/{function_id}/runs
  /^functions\/[^\/]+\/runs\/[^\/]+$/, // /functions/{function_id}/runs/{run_id}
  /^functions\/[^\/]+\/runs\/start$/, // /functions/{function_id}/runs/start
  /^functions\/[^\/]+\/schedule$/, // /functions/{function_id}/schedule
  /^functions\/health$/, // /functions/health

  // Mailboxes endpoints
  /^mailboxes$/, // /mailboxes
  /^mailboxes\/[^\/]+$/, // /mailboxes/{mailbox_id}
  /^mailboxes\/connect-token$/, // /mailboxes/connect-token
  /^mailboxes\/sync$/, // /mailboxes/sync

  // Managed-auth endpoints
  /^managed-auth\/connect-links$/, // /managed-auth/connect-links
  /^managed-auth\/connect-links\/context$/, // /managed-auth/connect-links/context
  /^managed-auth\/connect-links\/mailboxes$/, // /managed-auth/connect-links/mailboxes
  /^managed-auth\/connect-links\/mailboxes\/connect$/, // /managed-auth/connect-links/mailboxes/connect
  /^managed-auth\/connect-links\/mailboxes\/sync$/, // /managed-auth/connect-links/mailboxes/sync
  /^managed-auth\/connect-links\/status$/, // /managed-auth/connect-links/status
  /^managed-auth\/connect-links\/submit$/, // /managed-auth/connect-links/submit

  // Personas endpoints
  /^personas$/, // /personas
  /^personas\/[^\/]+$/, // /personas/{persona_id}
  /^personas\/[^\/]+\/emails$/, // /personas/{persona_id}/emails
  /^personas\/[^\/]+\/sms$/, // /personas/{persona_id}/sms
  /^personas\/create$/, // /personas/create

  // Profiles endpoints
  /^profiles$/, // /profiles
  /^profiles\/[^\/]+$/, // /profiles/{profile_id}
  /^profiles\/[^\/]+\/cookies$/, // /profiles/{profile_id}/cookies
  /^profiles\/[^\/]+\/duplicate$/, // /profiles/{profile_id}/duplicate
  /^profiles\/create$/, // /profiles/create

  // Prompts endpoints
  /^prompts\/improve$/, // /prompts/improve
  /^prompts\/nudge$/, // /prompts/nudge

  // Proxies endpoints
  /^proxies\/gateway\/credentials$/, // /proxies/gateway/credentials

  // Ready endpoints
  /^ready$/, // /ready

  // Root endpoints
  /^health$/, // /health
  /^scrape$/, // /scrape
  /^scrape_from_html$/, // /scrape_from_html

  // Search endpoints
  /^search$/, // /search

  // Secrets endpoints
  /^secrets$/, // /secrets
  /^secrets\/[^\/]+$/, // /secrets/{name}
  /^secrets\/[^\/]+$/, // /secrets/{secret_id}

  // Sessions endpoints
  /^sessions$/, // /sessions
  /^sessions\/[^\/]+$/, // /sessions/{session_id}
  /^sessions\/[^\/]+\/cookies$/, // /sessions/{session_id}/cookies
  /^sessions\/[^\/]+\/debug$/, // /sessions/{session_id}/debug
  /^sessions\/[^\/]+\/files$/, // /sessions/{session_id}/files
  /^sessions\/[^\/]+\/files\/[^\/]+$/, // /sessions/{session_id}/files/{file_id}
  /^sessions\/[^\/]+\/network\/logs$/, // /sessions/{session_id}/network/logs
  /^sessions\/[^\/]+\/offset$/, // /sessions/{session_id}/offset
  /^sessions\/[^\/]+\/page\/execute$/, // /sessions/{session_id}/page/execute
  /^sessions\/[^\/]+\/page\/observe$/, // /sessions/{session_id}/page/observe
  /^sessions\/[^\/]+\/page\/scrape$/, // /sessions/{session_id}/page/scrape
  /^sessions\/[^\/]+\/page\/screenshot$/, // /sessions/{session_id}/page/screenshot
  /^sessions\/[^\/]+\/replay$/, // /sessions/{session_id}/replay
  /^sessions\/[^\/]+\/stop$/, // /sessions/{session_id}/stop
  /^sessions\/[^\/]+\/workflow\/code$/, // /sessions/{session_id}/workflow/code
  /^sessions\/start$/, // /sessions/start

  // Usage endpoints
  /^usage$/, // /usage
  /^usage\/logs$/, // /usage/logs

  // Vaults endpoints
  /^vaults$/, // /vaults
  /^vaults\/[^\/]+$/, // /vaults/{vault_id}
  /^vaults\/[^\/]+\/card$/, // /vaults/{vault_id}/card
  /^vaults\/[^\/]+\/credentials$/, // /vaults/{vault_id}/credentials
  /^vaults\/create$/, // /vaults/create
];

export interface PathValidationResult {
  isValid: boolean;
  error?: string;
}

/**
 * Validates a request path against a list of allowed patterns.
 * Prevents directory traversal and SSRF attacks.
 */
export function validatePath(
  pathSegments: string[],
  allowedPatterns: RegExp[],
): PathValidationResult {
  const path = pathSegments.join('/');

  // Check for directory traversal attempts
  if (path.includes('..') || path.includes('//') || path.startsWith('/')) {
    return {
      isValid: false,
      error: 'Invalid path: directory traversal detected',
    };
  }

  // Check against allowed patterns
  const isValidPattern = allowedPatterns.some((pattern) => pattern.test(path));
  if (!isValidPattern) {
    return {
      isValid: false,
      error: `Invalid path: ${path} does not match any allowed endpoint pattern`,
    };
  }

  return { isValid: true };
}
