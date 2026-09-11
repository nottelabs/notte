export { checkForLatestVersion, startVersionCheck } from '@/version-check';

// Re-export all generated types and services
export * from '@/lib/client/types.gen';
export * from '@/lib/client/sdk.gen';

// Re-export client for direct access
export { client } from '@/lib/client/client.gen';

// Export main SDK classes
export { NotteClient, DEFAULT_NOTTE_API_URL, DEFAULT_REQUEST_TIMEOUT_MS, TIMEOUT_HEADER } from '@/client';
export { Session } from '@/session';
export { Agent } from '@/agent';
export { NotteVault } from '@/vaults';
export { NottePersona } from '@/personas';
export { NotteFunction } from '@/functions';
export { Encryption } from '@/encryption';
export { SessionFiles } from '@/files';
export type { FileSource, SessionFile, SessionFilesPage } from '@/files';

// Errors and helpers
export {
  NotteError,
  NotteAPIError,
  NotteAPIExecutionError,
  AuthenticationError,
  InvalidRequestError,
  NotteTimeoutError,
  FailedToRunCloudFunctionError,
  ScrapeFailedError,
  ActionExecutionError,
  EvaluateJsNoDataError,
  FetchResponseDecodeError,
  retry,
} from '@/errors';
export type { NotteAPIErrorBody, RetryOptions } from '@/errors';

// Scrape helpers shared by `client.scrape()` and `session.scrape()`
export { processScrapeResponse } from '@/scrape';
export type { ScrapeOptions, ScrapeResult, SessionScrapeOptions, StructuredData, ZodLikeSchema } from '@/scrape';

// Export types
export type {
  NotteClientConfig,
  GlobalScrapeOptions,
  SessionListOptions,
  AgentListOptions,
  VaultListOptions,
  FunctionListOptions,
} from '@/client';
export type { SessionOptions } from '@/session';
export type { AgentConstructor, AgentRunRequest, AgentUpdateHandler } from '@/agent';
export { prepareAgentRequest, parseAgentStatusMessage } from '@/agent';
export type { VaultConstructor } from '@/vaults';
export type { PersonaConstructor, MessageReadOptions, PersonaListOptions, PersonaResponseWithInternalEmail } from '@/personas';
export type {
  FunctionConstructor,
  FunctionRunOptions,
  FunctionRunStartResult,
  FunctionRunResult,
  FunctionRunCreateResult,
  FunctionRunListOptions,
  FunctionUrlOptions,
  FunctionDownloadOptions,
} from '@/functions';

// Export proxy types and errors (the proxy module itself is available via 'notte-sdk/next' and 'notte-sdk/proxy')
export type { NotteProxyConfig } from '@/proxy/types';
export { NotteProxyAuthError } from '@/proxy/types';

// Create a configured client instance (legacy support)
import { createClient as createGeneratedClient } from '@/lib/client/client';
import { DEFAULT_NOTTE_API_URL as DEFAULT_API_URL } from '@/client';

export const createClient = (config?: { baseUrl?: string; token?: string }) => {
  const client = createGeneratedClient({ baseUrl: config?.baseUrl || DEFAULT_API_URL });
  if (config?.baseUrl) {
    client.setConfig({ baseUrl: config.baseUrl });
  }

  if (config?.token) {
    client.interceptors.request.use((request: any) => {
      request.headers.set('Authorization', `Bearer ${config.token}`);
      return request;
    });
  }

  return client;
};

// Default export - NotteClient for convenience
export { NotteClient as default } from '@/client';
