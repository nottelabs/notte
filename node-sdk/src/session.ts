import { NotteClient } from '@/client';
import type {
  SessionResponse,
  ReplayResponse,
  ApiSessionStartRequest,
  Cookie,
  ExecutionResponse,
  ApiExecutionResponse,
  ActionSpace,
  GetCookiesResponse,
  Observation,
  ScrapeRequest,
  DataSpace,
  ScrapeSchemaResponse
} from '@/lib/client/types.gen';
import {
  sessionStart,
  sessionStop,
  sessionStatus,
  sessionCookiesSet,
  sessionCookiesGet,
  pageExecute,
  pageObserve,
  sessionReplay,
  pageScrape
} from '@/lib/client/sdk.gen';
import { formatError, openBrowser } from '@/utils';
import { z } from 'zod';

/**
 * Post-process scrape response based on options
 */
export function processScrapeResponse(scrapeResponse: any, options: any): string | any {
  // Post-processing logic based on options
  if (options.only_images && scrapeResponse.images) {
    return scrapeResponse.images;
  }

  // Check if structured data is required
  if (requiresSchema(options)) {
    const structured = scrapeResponse.structured;
    if (!structured) {
      throw new Error('Failed to scrape structured data. This should not happen. Please report this issue.');
    }

    // If response_format is a Zod schema, try to validate structured.data
    if (options.response_format && typeof options.response_format.parse === 'function') {
      if (structured.data) {
        try {
          const validatedData = options.response_format.parse(structured.data);
          return validatedData;
        } catch (error) {
          throw new Error(`Schema validation failed: ${error instanceof Error ? error.message : String(error)}`);
        }
      }
      // If no data available, return the structured response as-is
      return structured;
    }

    // For JSON schemas, return the structured data as-is
    return structured;
  }

  // If we have a Zod schema but no structured data, try to parse the raw data
  if (options.response_format && typeof options.response_format.parse === 'function') {
    try {
      // Try to parse the entire response data
      const validatedData = options.response_format.parse(scrapeResponse);
      return validatedData;
    } catch (error) {
      throw new Error(`Schema validation failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  // Return markdown by default
  return scrapeResponse.markdown;
}

/**
 * Check if the scrape request requires schema validation
 */
function requiresSchema(options: any): boolean {
  return !!(options.response_format || options.instructions);
}

export interface SessionOptions extends Omit<ApiSessionStartRequest, 'use_file_storage'> {
  /**
   * @deprecated Remote sessions always use the supported browser launch mode.
   * Retained as a boolean so existing typed configuration still compiles.
   * `true` is discarded; `false` raises a migration error when starting.
   */
  headless?: boolean;
  /**
   * Open the live viewer in the local default browser after the session starts.
   * This is a local SDK option and is not sent to the API.
   */
  open_viewer?: boolean;
}

export class Session {
  private client: NotteClient;
  private options: ApiSessionStartRequest;
  private openViewer: boolean;
  private legacyHeadless: boolean | undefined;
  private sessionId: string | null = null;
  private isActive = false;
  private response: SessionResponse | null = null;

  constructor(client: NotteClient, options: SessionOptions = {}) {
    this.client = client;
    const { open_viewer = false, headless, ...sessionOptions } = options;
    this.options = sessionOptions;
    this.openViewer = open_viewer;
    this.legacyHeadless = headless;
  }

  /**
   * Start the session - creates a new session on the server
   */
  async start(): Promise<void> {
    if (this.legacyHeadless === false) {
      throw new Error(
        'Remote `headless: false` is no longer supported. `headless: true` sessions still include session replays and access to the live viewer.'
      );
    }
    if (this.legacyHeadless === true) {
      console.warn('`headless: true` is deprecated and ignored; remote sessions always use the supported browser launch mode.');
      this.legacyHeadless = undefined;
    }
    if (this.isActive) {
      throw new Error('Session is already active');
    }

    let shouldOpenViewer = false;
    try {
      // Use the generated client to create a session
      const response = await sessionStart({
        client: this.client.getClient(),
        body: this.options
      });

      if (response?.error) {
        throw new Error(`Failed to create session: ${formatError(response.error)}`);
      }

      const sessionData = response.data as SessionResponse;
      this.sessionId = sessionData.session_id;
      this.isActive = true;
      this.response = sessionData;
      shouldOpenViewer = this.openViewer;
    } catch (error) {
      throw new Error(`Failed to start session: ${error instanceof Error ? error.message : String(error)}`);
    }

    if (shouldOpenViewer) {
      this.openViewerInBrowser();
    }
  }

  /**
   * Stop the session - terminates the session on the server
   */
  async stop(closeReason: 'manual' | 'error' = 'manual'): Promise<void> {
    if (!this.isActive || !this.sessionId) {
      return;
    }
    const response = await sessionStop({
      client: this.client.getClient(),
      path: {
        session_id: this.sessionId
      },
      query: {
        close_reason: closeReason
      }
    });

    if (response?.error) {
      throw new Error(`Failed to stop session: ${formatError(response.error)}`);
    }
    this.response = response.data as SessionResponse;
    this.isActive = false;
    this.sessionId = null;
  }

  /**
   * Get session status
   */
  async status(): Promise<SessionResponse> {
    if (!this.sessionId) {
      throw new Error('Session not started');
    }

    const response = await sessionStatus({
      client: this.client.getClient(),
      path: {
        session_id: this.sessionId
      }
    });

    if (response?.error) {
      throw new Error(`Failed to get session status: ${formatError(response.error)}`);
    }

    return response.data as SessionResponse;
  }

  /**
   * Get session ID
   */
  getId(): string | null {
    return this.sessionId;
  }

  /**
   * Check if session is active
   */
  isSessionActive(): boolean {
    return this.isActive;
  }

  /**
   * Get the last response from session operations
   */
  getResponse(): SessionResponse | null {
    return this.response;
  }

  /**
   * Open the live viewer for this session in the local default browser.
   */
  viewer(): void {
    if (!this.sessionId) {
      throw new Error('Session not started');
    }

    const viewerUrl = this.response?.viewer_url;
    if (!viewerUrl) {
      throw new Error('No viewer URL available for this session');
    }

    openBrowser(viewerUrl);
  }

  private openViewerInBrowser(): void {
    const viewerUrl = this.response?.viewer_url;
    if (!viewerUrl) {
      console.warn('[Session] No viewer URL available; session started without opening a viewer.');
      return;
    }

    openBrowser(viewerUrl);
  }

  /**
   * Set cookies for the session
   */
  async setCookies(cookies: Cookie[]): Promise<ExecutionResponse> {
    if (!this.sessionId) {
      throw new Error('Session not started');
    }

    const response = await sessionCookiesSet({
      client: this.client.getClient(),
      path: {
        session_id: this.sessionId
      },
      body: {
        cookies
      }
    });

    if (response?.error) {
      throw new Error(`Failed to set cookies: ${formatError(response.error)}`);
    }

    return response.data as ExecutionResponse;
  }

  /**
   * Set cookies from a file
   */
  async setCookiesFromFile(cookieFile: string): Promise<ExecutionResponse> {
    const fs = await import('fs/promises');
    const cookieData = await fs.readFile(cookieFile, 'utf-8');
    const cookies = JSON.parse(cookieData) as Cookie[];
    return this.setCookies(cookies);
  }

  /**
   * Get cookies from the session
   */
  async getCookies(): Promise<Cookie[]> {
    if (!this.sessionId) {
      throw new Error('Session not started');
    }

    const response = await sessionCookiesGet({
      client: this.client.getClient(),
      path: {
        session_id: this.sessionId
      }
    });

    if (response?.error) {
      throw new Error(`Failed to get cookies: ${formatError(response.error)}`);
    }

    return response.data.cookies;
  }

  /**
   * Execute an action on the page
   */
  async execute(action: any, raiseOnFailure: boolean = true): Promise<ApiExecutionResponse> {
    if (!this.sessionId) {
      throw new Error('Session not started');
    }

    const response = await pageExecute({
      client: this.client.getClient(),
      path: {
        session_id: this.sessionId
      },
      body: action
    });

    if (response?.error) {
      throw new Error(`Failed to execute action: ${formatError(response.error)}`);
    }

    const result = response.data as ApiExecutionResponse;

    if (raiseOnFailure && !result.success) {
      throw new Error(`Action execution failed: ${result.message}`);
    }

    return result;
  }

  /**
   * Observe the current page state
   */
  async observe(perceptionType: 'fast' | 'deep' = 'fast'): Promise<Observation> {
    if (!this.sessionId) {
      throw new Error('Session not started');
    }

    const response = await pageObserve({
      client: this.client.getClient(),
      path: {
        session_id: this.sessionId
      },
      body: {
        perception_type: perceptionType
      }
    });

    if (response?.error) {
      throw new Error(`Failed to observe page: ${formatError(response.error)}`);
    }

    return response.data;
  }

  /**
   * Get session replay data
   */
  async replay(): Promise<ReplayResponse> {
    // Replays are generated after stop(), which clears the active session ID.
    const sessionId = this.sessionId ?? this.response?.session_id;
    if (!sessionId) {
      throw new Error('Session not started');
    }

    const response = await sessionReplay({
      client: this.client.getClient(),
      path: {
        session_id: sessionId
      }
    });

    if (response?.error) {
      throw new Error(`Failed to get session replay: ${formatError(response.error)}`);
    }

    if (!response.data) {
      throw new Error('Failed to get session replay: empty response');
    }
    return response.data;
  }

  /**
   * Scrape the current page
   */
  async scrape(options?: ScrapeRequest): Promise<string | any>;
  async scrape<T>(options: ScrapeRequest & { response_format: z.ZodSchema<T>; json_schema?: any }): Promise<T>;
  async scrape<T = any>(options: ScrapeRequest & { response_format?: z.ZodSchema<T> | any; json_schema?: any } = {}): Promise<string | T | any> {
    if (!this.sessionId) {
      throw new Error('Session not started');
    }

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

    const response = await pageScrape({
      client: this.client.getClient(),
      path: {
        session_id: this.sessionId
      },
      body: apiOptions
    });

    if (response?.error) {
      throw new Error(`Failed to scrape page: ${JSON.stringify(response.error)}`);
    }
    return processScrapeResponse(response.data, options);
  }

  /**
   * Context manager pattern - automatically start and stop session
   * Usage: await session.use(async (session) => { ... })
   */
  async use<T>(callback: (session: Session) => Promise<T>): Promise<T> {
    await this.start();
    let callbackFailed = false;
    try {
      return await callback(this);
    } catch (error) {
      callbackFailed = true;
      throw error;
    } finally {
      try {
        await this.stop(callbackFailed ? 'error' : 'manual');
      } catch (stopError) {
        if (!callbackFailed) {
          throw stopError;
        }
        console.error('[Session] Failed to stop session after callback error:', stopError);
      }
    }
  }

  /**
   * Async iterator pattern for session lifecycle management
   * Usage: for await (const session of sessionInstance) { ... }
   */
  async *[Symbol.asyncIterator]() {
    await this.start();
    try {
      yield this;
    } finally {
      await this.stop();
    }
  }
}
