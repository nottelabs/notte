/** The Notte API used when no base URL is configured and the credential is not an EU one. */
export const DEFAULT_NOTTE_API_URL = 'https://api.notte.cc';
/** The Notte API that serves EU credentials. */
export const EU_NOTTE_API_URL = 'https://eu-api.notte.cc';

// API keys and access tokens name their data region in their prefix. The API
// applies the same rule; any other credential belongs to the default region.
const EU_CREDENTIAL_PREFIXES = ['sk-notte-eu-', 'sk-notte-org-eu-', 'nat_eu_'];

/**
 * The API a credential is served by when no base URL is configured.
 *
 * EU credentials (`sk-notte-eu-...`, `sk-notte-org-eu-...`, `nat_eu_...`) use
 * the EU API; every other credential, or none, uses the default API. An
 * explicit `baseUrl` or `NOTTE_API_URL` takes precedence over this.
 */
export function defaultApiUrl(apiKey?: string | null): string {
  if (apiKey && EU_CREDENTIAL_PREFIXES.some((prefix) => apiKey.startsWith(prefix))) {
    return EU_NOTTE_API_URL;
  }
  return DEFAULT_NOTTE_API_URL;
}
