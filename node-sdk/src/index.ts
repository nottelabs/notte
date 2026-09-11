export { checkForLatestVersion } from '@/version-check';

// Re-export all generated types and services
export * from '@/lib/client/types.gen';
export * from '@/lib/client/sdk.gen';

// Re-export client for direct access
export { client } from '@/lib/client/client.gen';

// Export main SDK classes
export { NotteClient } from '@/client';
export { Session } from '@/session';
export { Agent } from '@/agent';
export { NotteVault } from '@/vaults';
export { NottePersona } from '@/personas';
export { NotteFunction } from '@/functions';
export { Encryption } from '@/encryption';
export { SessionFiles } from '@/files';
export type { FileSource, SessionFile, SessionFilesPage } from '@/files';

// Export types
export type { NotteClientConfig } from '@/client';
export type { SessionOptions } from '@/session';
export type { AgentConstructor, AgentRunRequest, AgentUpdateHandler } from '@/agent';
export type { VaultConstructor } from '@/vaults';
export type { PersonaConstructor, MessageReadOptions, PersonaListOptions } from '@/personas';
export type { FunctionConstructor, FunctionRunOptions, FunctionRunStartResult, FunctionRunResult, FunctionRunCreateResult, FunctionUrlOptions, FunctionDownloadOptions } from '@/functions';

// Export proxy types and errors (the proxy module itself is available via '@notte/sdk/next' and '@notte/sdk/proxy')
export type { NotteProxyConfig } from '@/proxy/types';
export { NotteProxyAuthError } from '@/proxy/types';

// Create a configured client instance (legacy support)
import { createClient as createGeneratedClient } from '@/lib/client/client';

export const createClient = (config?: { baseUrl?: string; token?: string }) => {
  const client = createGeneratedClient({ baseUrl: config?.baseUrl || 'https://api.notte.cc' });
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
