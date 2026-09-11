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
export { SessionFiles, RemoteFileStorage, FileNotFoundError, FileExistsError, sanitizeFilename } from '@/files';
export type { FileSource, SessionFile, SessionFilesPage, FileListOptions, FileDownloadOptions, UploadableFile } from '@/files';

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
export type {
  SessionOptions,
  ExecuteOptions,
  ReplayOptions,
  SessionScriptOptions,
  PerceptionType,
  SessionCloseReason,
} from '@/session';
export {
  CLUSTER_OVERLOAD_RETRY_DELAY_MS,
  SESSION_START_TRIES,
  CAPTCHA_SOLVE_TIMEOUT_MS,
  observeServerOwnedDialog,
  installServerOwnedDialogPolicy,
} from '@/session';

// Typed actions for `session.execute()` (`import { actions } from 'notte-sdk'`)
export { actions, isCaptchaSolveAction } from '@/actions';
export type { ExecuteAction, ActionType, ActionOfType, ActionInput } from '@/actions';

// In-page fetch helpers used by `session.fetch()`
export { PageFetchResponse, PageFetchHTTPError, buildFetchScript, responseFromEvaluated } from '@/page-fetch';
export type { PageFetchOptions, FetchData } from '@/page-fetch';

// Cookie file helpers
export { readCookiesFile, createOrAppendCookiesToFile } from '@/cookies';
export type { AgentConstructor, AgentRunRequest, AgentUpdateHandler } from '@/agent';
export { prepareAgentRequest, parseAgentStatusMessage } from '@/agent';
export type { VaultConstructor, VaultConstructorWithId, VaultConstructorCreate, CredentialField } from '@/vaults';
export { getRootDomain, validateUrl, validateMfaSecret, isValidMfaSecret, validateCredentials, CREDENTIAL_FIELDS } from '@/vaults';
export type { PersonaConstructor, MessageReadOptions, PersonaListOptions, PersonaResponseWithInternalEmail } from '@/personas';
export type {
  FunctionConstructor,
  FunctionConstructorWithId,
  FunctionConstructorCreate,
  FunctionRuntime,
  FunctionRunStatus,
  FunctionRunResponse,
  FunctionRunOptions,
  FunctionRunStartResult,
  FunctionRunResult,
  FunctionRunCreateResult,
  FunctionRunCreateOptions,
  FunctionRunListOptions,
  FunctionGetOptions,
  FunctionUpdateOptions,
  FunctionMetadataUpdateOptions,
  FunctionScheduleOptions,
  FunctionRollbackOptions,
  FunctionUrlOptions,
  FunctionDownloadOptions,
} from '@/functions';
export { FUNCTION_RUN_TIMEOUT_MS, FUNCTION_RUN_ENDPOINTS, RUN_API_KEY_HEADER } from '@/functions';

// Top-level API wrappers
export type {
  SearchOptions,
  SearchResponse,
  SearchResultItem,
  SearchResultsResponse,
  SearchSource,
  SearchSourcedAnswerResponse,
  SearchStructuredResponse,
} from '@/search';
export { NotteAnything } from '@/anything';
export type { AnythingStartOptions, AnythingStartResponse } from '@/anything';
export { NotteSecrets } from '@/secrets';
export type { SecretListOptions, SecretStoreOptions } from '@/secrets';
export { NotteUsage } from '@/usage';
export type { UsageOptions, UsageLogsOptions, UsageLogEndpoint } from '@/usage';

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
