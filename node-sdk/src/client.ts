import { createClient } from '@/lib/client/client';
import { Session, type SessionOptions } from '@/session';
import type { GlobalScrapeRequest } from '@/lib/client/types.gen';
import { Agent, type AgentConstructor } from '@/agent';
import { NotteVault, type VaultConstructor } from '@/vaults';
import { NottePersona, type PersonaConstructor, type PersonaListOptions } from '@/personas';
import { NotteFunction, type FunctionConstructor } from '@/functions';
import { scrapeWebpage, listPersonas } from '@/lib/client/sdk.gen';
import { processScrapeResponse } from '@/session';
import { z } from 'zod';
import type { PersonaResponse } from '@/lib/client/types.gen';
import { SDK_VERSION } from '@/version';
import { SessionFiles } from '@/files';


export interface NotteClientConfig {
  /** API base URL. Defaults to NOTTE_API_URL, then https://api.notte.cc. */
  baseUrl?: string;
  /** API key. Defaults to NOTTE_API_KEY; required except when using a relative proxy URL. */
  apiKey?: string;
}

/** Entry point for sessions, agents, functions, vaults, personas, and session files. */
export class NotteClient {
  private config: NotteClientConfig;
  private readonly client = createClient();

  constructor(config: NotteClientConfig = {}) {
    // Get API key from config or environment variable
    const apiKey = config.apiKey || process.env.NOTTE_API_KEY;
    const baseUrl = config.baseUrl || process.env.NOTTE_API_URL || 'https://api.notte.cc';

    // Only skip the apiKey check for relative proxy paths (e.g. '/api/notte').
    // Any HTTPS URL—including staging—still requires a key.
    const isProxyMode = /^\/(?!\/)/.test(baseUrl);
    if (!isProxyMode) {
      const url = new URL(baseUrl);
      const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
      if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) {
        throw new Error('API base URL must use HTTPS (HTTP is only allowed on loopback for local development)');
      }
    }
    if (!apiKey && !isProxyMode) {
      throw new Error('API key is required. Provide it via config.apiKey or set the NOTTE_API_KEY environment variable.');
    }

    this.config = {
      baseUrl,
      apiKey,
    };

    // Use redirect:'manual' so we handle 3xx ourselves.
    // Node's undici drops POST bodies on cross-origin 307 redirects
    // (e.g. when the API gateway redirects to AWS Lambda function URLs).
    this.client.setConfig({
      baseUrl: this.config.baseUrl,
      redirect: 'manual',
    });

    this.client.interceptors.request.use((request: any) => {
      if (this.config.apiKey) request.headers.set('Authorization', `Bearer ${this.config.apiKey}`);
      request.headers.set('x-notte-request-origin', 'sdk-node');
      request.headers.set('x-notte-sdk-version', SDK_VERSION);
      return request;
    });

    // Follow 307/308 redirects manually, replaying the original body.
    // Also normalizes Content-Type from text/plain to application/json
    // (AWS Lambda function URLs return JSON with the wrong Content-Type).
    this.client.interceptors.response.use(async (response: any, request: any, opts: any) => {
      if ((response.status === 307 || response.status === 308) && response.headers.get('location')) {
        const location = response.headers.get('location')!;
        const headers = new Headers(request.headers);
        // Strip auth on cross-origin redirects to avoid leaking credentials
        if (new URL(location).origin !== new URL(request.url).origin) {
          headers.delete('Authorization');
        }
        const headerRecord: Record<string, string> = {};
        headers.forEach((v: string, k: string) => { headerRecord[k] = v; });
        const redirected = await fetch(location, {
          method: request.method,
          headers: headerRecord,
          body: opts.serializedBody ?? undefined,
        });
        return redirected;
      }

      // Normalize text/plain → application/json (Lambda function URLs)
      const ct = response.headers.get('content-type') ?? '';
      if (opts.parseAs !== 'stream' && ct.split(';')[0]?.trim() === 'text/plain') {
        const body = await response.arrayBuffer();
        const headers = new Headers(response.headers);
        headers.set('content-type', 'application/json');
        return new Response(body, { status: response.status, statusText: response.statusText, headers });
      }

      return response;
    });
  }

  /**
   * Create a new session
   */
  Session(options: SessionOptions = {}): Session {
    return new Session(this, options);
  }

  /** Access files owned by a specific session, including closed sessions. */
  Files(sessionId: string): SessionFiles {
    return new SessionFiles(this.getClient(), sessionId);
  }

  /**
   * Create a new agent
   */
  Agent(options: AgentConstructor): Agent {
    return new Agent(this, options);
  }

  /**
   * Create or access a vault
   */
  Vault(options?: VaultConstructor): NotteVault {
    return new NotteVault(this, options);
  }

  /**
   * Create or access a persona
   */
  Persona(options?: PersonaConstructor): NottePersona {
    return new NottePersona(this, options);
  }

  /**
   * Create or access a function
   */
  NotteFunction(options: FunctionConstructor): NotteFunction {
    return new NotteFunction(this, options);
  }

  /**
   * Personas client for listing and managing personas
   */
  get personas() {
    return {
      list: async (options?: PersonaListOptions): Promise<PersonaResponse[]> => {
        const response = await listPersonas({
          client: this.getClient(),
          query: options || {}
        });

        if (response?.error) {
          throw new Error(`Failed to list personas: ${JSON.stringify(response.error)}`);
        }

        return (response.data as any)?.items || [];
      }
    };
  }

  /**
   * Get the configured client instance
   */
  getClient() {
    return this.client;
  }

  /**
   * Scrape a webpage directly (without session)
   */
  async scrape(url: string, options?: Omit<GlobalScrapeRequest, 'url'>): Promise<string | any>;
  async scrape<T>(url: string, options: Omit<GlobalScrapeRequest, 'url'> & { response_format: z.ZodSchema<T>; json_schema?: any }): Promise<T>;
  async scrape<T = any>(url: string, options: Omit<GlobalScrapeRequest, 'url'> & { response_format?: z.ZodSchema<T> | any; json_schema?: any } = {}): Promise<string | T | any> {
    // If response_format is a Zod schema, we need to convert it to JSON schema for the API
    const apiOptions = { ...options };
    if (options.response_format && typeof options.response_format.parse === 'function') {
      // Use provided JSON schema or convert Zod schema to JSON schema for API compatibility
      if (options.json_schema) {
        apiOptions.response_format = options.json_schema;
      } else {
        apiOptions.response_format = z.toJSONSchema(options.response_format);
      }

      // Add more specific instructions to help the API understand what to extract
      if (!apiOptions.instructions) {
        // Try to infer what kind of data to extract from the schema structure
        const schemaStr = JSON.stringify(apiOptions.response_format);
        if (schemaStr.includes('plans') || schemaStr.includes('plan')) {
          apiOptions.instructions = "Extract pricing plans from the page";
        } else if (schemaStr.includes('products') || schemaStr.includes('product')) {
          apiOptions.instructions = "Extract product information from the page";
        } else if (schemaStr.includes('articles') || schemaStr.includes('article')) {
          apiOptions.instructions = "Extract article information from the page";
        } else {
          apiOptions.instructions = "Extract structured data from the page based on the provided schema";
        }
      }
    }

    const response = await scrapeWebpage({
      client: this.getClient(),
      body: {
        url,
        ...apiOptions
      }
    });

    if (response?.error) {
      throw new Error(`Failed to scrape webpage: ${JSON.stringify(response.error)}`);
    }

    const scrapeResponse = response.data;
    return processScrapeResponse(scrapeResponse, options);
  }

  /**
   * Get the client configuration
   */
  getConfig(): NotteClientConfig {
    return this.config;
  }
}
