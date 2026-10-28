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

  // Audit-events endpoints
  /^audit-events$/, // /audit-events

  // Data endpoints
  /^data$/, // /data
  /^data\/analytics$/, // /data/analytics
  /^data\/analytics\/requests$/, // /data/analytics/requests
  /^data\/analytics\/requests\/[^\/]+$/, // /data/analytics/requests/{request_id}
  /^data\/brand\/retrieve$/, // /data/brand/retrieve
  /^data\/cache$/, // /data/cache
  /^data\/maps\/search$/, // /data/maps/search
  /^data\/monitors$/, // /data/monitors
  /^data\/monitors\/[^\/]+$/, // /data/monitors/{monitor_id}
  /^data\/monitors\/[^\/]+\/changes$/, // /data/monitors/{monitor_id}/changes
  /^data\/monitors\/[^\/]+\/changes\/[^\/]+$/, // /data/monitors/{monitor_id}/changes/{change_id}
  /^data\/monitors\/[^\/]+\/run$/, // /data/monitors/{monitor_id}/run
  /^data\/monitors\/[^\/]+\/runs$/, // /data/monitors/{monitor_id}/runs
  /^data\/monitors\/[^\/]+\/runs\/[^\/]+$/, // /data/monitors/{monitor_id}/runs/{run_id}
  /^data\/monitors\/[^\/]+\/webhook\/rotate-secret$/, // /data/monitors/{monitor_id}/webhook/rotate-secret
  /^data\/monitors\/changes$/, // /data/monitors/changes
  /^data\/monitors\/credit-usage$/, // /data/monitors/credit-usage
  /^data\/monitors\/limits$/, // /data/monitors/limits
  /^data\/monitors\/runs$/, // /data/monitors/runs
  /^data\/news\/search$/, // /data/news/search
  /^data\/people\/enrich$/, // /data/people/enrich
  /^data\/products\/extract$/, // /data/products/extract
  /^data\/web\/fetch$/, // /data/web/fetch
  /^data\/web\/styleguide$/, // /data/web/styleguide
  /^data\/webhooks\/deliveries$/, // /data/webhooks/deliveries
  /^data\/webhooks\/deliveries\/[^\/]+$/, // /data/webhooks/deliveries/{delivery_id}
  /^data\/webhooks\/deliveries\/[^\/]+\/attempts$/, // /data/webhooks/deliveries/{delivery_id}/attempts
  /^data\/webhooks\/deliveries\/[^\/]+\/retry$/, // /data/webhooks/deliveries/{delivery_id}/retry
  /^data\/youtube\/extract$/, // /data/youtube/extract

  // Functions endpoints
  /^functions$/, // /functions
  /^functions\/[^\/]+$/, // /functions/{function_id}
  /^functions\/[^\/]+\/fork$/, // /functions/{function_id}/fork
  /^functions\/[^\/]+\/rollback$/, // /functions/{function_id}/rollback
  /^functions\/[^\/]+\/rollback\/conditional$/, // /functions/{function_id}/rollback/conditional
  /^functions\/[^\/]+\/runs$/, // /functions/{function_id}/runs
  /^functions\/[^\/]+\/runs\/[^\/]+$/, // /functions/{function_id}/runs/{run_id}
  /^functions\/[^\/]+\/runs\/[^\/]+\/payloads\/[^\/]+$/, // /functions/{function_id}/runs/{run_id}/payloads/{field}
  /^functions\/[^\/]+\/runs\/[^\/]+\/payloads\/[^\/]+\/upload$/, // /functions/{function_id}/runs/{run_id}/payloads/{field}/upload
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
  /^managed-auth\/connections\/[^\/]+\/check$/, // /managed-auth/connections/{connection_id}/check
  /^managed-auth\/connections\/[^\/]+\/reauthenticate$/, // /managed-auth/connections/{connection_id}/reauthenticate
  /^managed-auth\/connections\/[^\/]+\/refresh$/, // /managed-auth/connections/{connection_id}/refresh
  /^managed-auth\/operations\/[^\/]+$/, // /managed-auth/operations/{operation_id}

  // Payments endpoints
  /^payments\/[^\/]+$/, // /payments/{payment_id}
  /^payments\/connect$/, // /payments/connect
  /^payments\/disconnect$/, // /payments/disconnect

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
  /^profiles\/[^\/]+\/state$/, // /profiles/{profile_id}/state
  /^profiles\/create$/, // /profiles/create

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
  /^sessions\/[^\/]+\/auth$/, // /sessions/{session_id}/auth
  /^sessions\/[^\/]+\/cookies$/, // /sessions/{session_id}/cookies
  /^sessions\/[^\/]+\/debug$/, // /sessions/{session_id}/debug
  /^sessions\/[^\/]+\/files$/, // /sessions/{session_id}/files
  /^sessions\/[^\/]+\/files\/[^\/]+$/, // /sessions/{session_id}/files/{file_id}
  /^sessions\/[^\/]+\/network\/logs$/, // /sessions/{session_id}/network/logs
  /^sessions\/[^\/]+\/offset$/, // /sessions/{session_id}/offset
  /^sessions\/[^\/]+\/page\/execute$/, // /sessions/{session_id}/page/execute
  /^sessions\/[^\/]+\/page\/execute\/file$/, // /sessions/{session_id}/page/execute/file
  /^sessions\/[^\/]+\/page\/observe$/, // /sessions/{session_id}/page/observe
  /^sessions\/[^\/]+\/page\/scrape$/, // /sessions/{session_id}/page/scrape
  /^sessions\/[^\/]+\/page\/screenshot$/, // /sessions/{session_id}/page/screenshot
  /^sessions\/[^\/]+\/payments$/, // /sessions/{session_id}/payments
  /^sessions\/[^\/]+\/profile-preview$/, // /sessions/{session_id}/profile-preview
  /^sessions\/[^\/]+\/profile\/save$/, // /sessions/{session_id}/profile/save
  /^sessions\/[^\/]+\/replay$/, // /sessions/{session_id}/replay
  /^sessions\/[^\/]+\/replay\/mouse$/, // /sessions/{session_id}/replay/mouse
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
