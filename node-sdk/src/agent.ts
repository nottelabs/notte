import WebSocket from 'ws';
import { NotteClient } from '@/client';
import { Session } from '@/session';
import type {
  AgentResponse,
  LegacyAgentStatusResponse,
  ApiAgentStartRequest,
} from '@/lib/client/types.gen';
import {
  agentStart,
  agentStatus,
  agentStop,
  sessionDebugInfo
} from '@/lib/client/sdk.gen';
import { formatError } from '@/utils';
import { NotteVault } from './vaults';
import { NottePersona } from './personas';
import { z } from 'zod';

/**
 * If `response_format` is a Zod schema, convert it to JSON Schema for the API
 * and return the schema for later runtime validation of the agent's answer.
 * Mirrors the Zod handling on `session.scrape()`.
 */
export function prepareAgentRequest<T = unknown>(
  data: AgentRunRequest & { response_format?: z.ZodSchema<T> | unknown | null }
): { apiData: AgentRunRequest; zodSchema: z.ZodSchema<T> | null } {
  const apiData: AgentRunRequest = { ...data };
  const rf: any = data.response_format;
  if (rf && typeof rf.parse === 'function' && typeof rf.safeParse === 'function') {
    apiData.response_format = z.toJSONSchema(rf);
    return { apiData, zodSchema: rf as z.ZodSchema<T> };
  }
  return { apiData, zodSchema: null };
}

export function parseAgentStatusMessage(parsed: any, agentId: string): LegacyAgentStatusResponse | null {
  // Current backend log websocket sends final status wrapped as
  // { status: "agent_stop", agent: LegacyAgentStatusResponse }.
  if (
    parsed?.status === 'agent_stop' &&
    parsed.agent &&
    parsed.agent.agent_id === agentId &&
    parsed.agent.task !== undefined &&
    parsed.agent.status !== undefined
  ) {
    return parsed.agent as LegacyAgentStatusResponse;
  }

  // Older/unwrapped shape: the final message is the status response itself.
  if (parsed?.agent_id === agentId && parsed.task !== undefined && parsed.status !== undefined) {
    return parsed as LegacyAgentStatusResponse;
  }

  return null;
}

// Overloads for constructor - mirrors Python overloads
export interface AgentConstructorWithSession extends Omit<ApiAgentStartRequest, 'session_id' | 'vault_id' | 'persona_id' | 'task' | 'response_format' | 'url'> {
  session: Session;
  vault?: NotteVault;
  persona?: NottePersona;
  vault_id?: string;
  persona_id?: string;
  agent_id?: never;
}

export interface AgentConstructorWithAgentId {
  agent_id: string;
  session?: never;
  vault?: never;
  persona?: never;
}

export type AgentConstructor = AgentConstructorWithSession | AgentConstructorWithAgentId | ApiAgentStartRequest;

export type AgentUpdateHandler = (update: {
  type: 'status' | 'step' | 'completion';
  data: any;
  timestamp: string;
}) => void;

/**
 * Validate persona option and return persona_id if valid
 */
function validatePersonaOption(persona?: NottePersona, persona_id?: string): string | undefined {
  if (persona) {
    // If persona object is provided, validate it has a valid personaId
    try {
      const personaId = persona.personaId;
      if (!personaId || personaId.length === 0) {
        throw new Error('Persona ID cannot be empty');
      }
      return personaId;
    } catch (error) {
      throw new Error(`Invalid persona object: ${error instanceof Error ? error.message : String(error)}`);
    }
  } else if (persona_id) {
    // If persona_id string is provided, validate it's not empty
    if (persona_id.length === 0) {
      throw new Error('Persona ID cannot be empty');
    }
    return persona_id;
  }
  return undefined;
}

/**
 * Validate vault option and return vault_id if valid
 */
function validateVaultOption(vault?: NotteVault, vault_id?: string): string | undefined {
  if (vault) {
    // If vault object is provided, validate it has a valid vaultId
    try {
      const vaultId = vault.vaultId;
      if (!vaultId || vaultId.length === 0) {
        throw new Error('Vault ID cannot be empty');
      }
      return vaultId;
    } catch (error) {
      throw new Error(`Invalid vault object: ${error instanceof Error ? error.message : String(error)}`);
    }
  } else if (vault_id) {
    // If vault_id string is provided, validate it's not empty
    if (vault_id.length === 0) {
      throw new Error('Vault ID cannot be empty');
    }
    return vault_id;
  }
  return undefined;
}

/**
 * Validate session option and return session_id if valid
 */
function validateSessionOption(session: Session): string {
  const sessionId = session.getId();
  if (!sessionId || sessionId.length === 0) {
    throw new Error('Session ID cannot be empty');
  }
  return sessionId;
}

/**
 * Validate agent_id option
 */
function validateAgentIdOption(agent_id: string): void {
  if (agent_id.length === 0) {
    throw new Error('Agent ID cannot be empty');
  }
}

// Default logger function that mimics Python's live_log_step behavior
const defaultStepLogger = (stepData: any, stepCounter: number, agentId: string) => {
  console.log(`✨ Step ${stepCounter} (agent: ${agentId})`);

  // If the step data has the expected structure, format it nicely
  if (stepData && typeof stepData === 'object') {
    if (stepData.state) {
      const state = stepData.state;

      // Format similar to Python render_agent_status
      if (state.page_summary) {
        console.log(`📝 Current page: ${state.page_summary}`);
      }

      if (state.previous_goal_eval) {
        const statusEmoji = state.previous_goal_status === 'success' ? '✅' :
          state.previous_goal_status === 'failure' ? '❌' : '❓';
        console.log(`🔬 Previous goal: ${statusEmoji} ${state.previous_goal_eval}`);
      }

      if (state.memory) {
        console.log(`🧠 Memory: ${state.memory}`);
      }

      if (state.next_goal) {
        console.log(`🎯 Next goal: ${state.next_goal}`);
      }

      if (state.relevant_interactions && state.relevant_interactions.length > 0) {
        console.log(`🆔 Relevant ids:`);
        state.relevant_interactions.forEach((interaction: any) => {
          console.log(`   ▶ ${interaction.id}: ${interaction.reason}`);
        });
      }
    }

    if (stepData.action) {
      const action = stepData.action;
      let actionStr = `⚡ Taking action:\n   ▶ ${action.name || action.type || 'Unknown action'}`;

      // Add parameter info if available
      if (action.id) {
        actionStr += ` with id ${action.id}`;
      } else if (action.param && action.param.name && action[action.param.name]) {
        actionStr += ` with ${action.param.name}=${action[action.param.name]}`;
      }

      console.log(actionStr);
    }
  } else {
    // Fallback: just log the raw data if structure is unexpected
    console.log(stepData);
  }

  console.log(''); // Empty line for readability
};

// Types for run method parameters - mirrors AgentRunRequestDict
export interface AgentRunRequest {
  task: string;
  url?: string | null;
  response_format?: unknown | null;
  session_offset?: number | null;
  reasoning_model?: string;
  use_vision?: boolean;
  max_steps?: number;
  vault_id?: string | null;
  persona_id?: string | null;
  notifier_config?: { [key: string]: unknown } | null;
  updateHandler?: AgentUpdateHandler | null;
}

export class Agent {
  private client: NotteClient;
  private request?: Omit<ApiAgentStartRequest, 'task'>;
  private response: AgentResponse | null = null;
  private websocket: WebSocket | null = null;
  private existingAgent: boolean;

  constructor(client: NotteClient, options: AgentConstructor) {
    this.client = client;

    // Handle the overloaded constructor patterns from Python
    if ('agent_id' in options && options.agent_id) {
      // Constructor for existing agent (agent_id provided)
      if (options.session) {
        throw new Error('Either session (for running a new agent) or agent_id (for accessing an existing agent) have to be provided, not both');
      }

      // Validate agent_id
      validateAgentIdOption(options.agent_id);

      this.existingAgent = true;
      // Store the agent_id for later use - we'll fetch the response when needed
      this.response = { agent_id: options.agent_id } as AgentResponse;

    } else if ('session' in options && options.session) {
      // Constructor for new agent (session provided)
      if (options.agent_id) {
        throw new Error('Either session (for running a new agent) or agent_id (for accessing an existing agent) have to be provided, not both');
      }
      this.existingAgent = false;

      // Extract session and create request - mirrors Python data["session_id"] = session.session_id
      const { session, vault, persona, ...requestData } = options;

      // Validate all options using helper functions
      const sessionId = validateSessionOption(session);
      const vaultId = validateVaultOption(vault, options.vault_id);
      const personaId = validatePersonaOption(persona, options.persona_id);

      this.request = {
        session_id: sessionId,
        vault_id: vaultId,
        persona_id: personaId,
        ...requestData
      };

    } else {
      throw new Error('Either session (for running a new agent) or agent_id (for accessing an existing agent) have to be provided');
    }
  }

  /**
   * Start an agent task (non-blocking) - mirrors Python start method
   */
  async start<T>(data: AgentRunRequest & { response_format: z.ZodSchema<T> }): Promise<AgentResponse>;
  async start(data: AgentRunRequest): Promise<AgentResponse>;
  async start<T>(data: AgentRunRequest & { response_format?: z.ZodSchema<T> | unknown | null }): Promise<AgentResponse> {
    if (this.existingAgent) {
      throw new Error('You cannot call start() on an agent instantiated from agent id');
    }

    if (!this.request) {
      throw new Error('Agent not properly initialized with session');
    }

    try {
      const { apiData } = prepareAgentRequest(data);
      const requestBody = {
        ...this.request,
        ...apiData
      };

      const response = await agentStart({
        client: this.client.getClient(),
        body: requestBody
      });

      if (response?.error) {
        throw new Error(`Failed to start agent: ${formatError(response.error)}`);
      }

      this.response = response.data as AgentResponse;
      return this.response;
    } catch (error) {
      throw new Error(`Failed to start agent: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Run agent task (blocking) - mirrors Python run method behavior
   * This is the main method that mirrors the Python SDK's run method
   */
  async run<T>(data: AgentRunRequest & { response_format: z.ZodSchema<T> }): Promise<LegacyAgentStatusResponse & { answer: T | null }>;
  async run(data: AgentRunRequest): Promise<LegacyAgentStatusResponse>;
  async run<T>(data: AgentRunRequest & { response_format?: z.ZodSchema<T> | unknown | null }): Promise<LegacyAgentStatusResponse> {
    if (this.existingAgent) {
      throw new Error('You cannot call run() on an agent instantiated from agent id');
    }

    const { apiData, zodSchema } = prepareAgentRequest<T>(data);

    // Start the agent first
    this.response = await this.start(apiData as AgentRunRequest);
    console.log(`[Agent] ${this.agentId} started`);

    // Then watch logs and wait for completion - mirrors Python arun method
    // Pass the updateHandler from the request to the watchLogsAndWait method
    const result = await this.watchLogsAndWait(true, data.updateHandler || null);

    // If a Zod schema was provided, validate the final answer.
    if (zodSchema && result && result.answer !== undefined && result.answer !== null) {
      let candidate: unknown;
      try {
        candidate = typeof result.answer === 'string' ? JSON.parse(result.answer) : result.answer;
      } catch {
        throw new Error(`Agent answer is not valid JSON and cannot be validated against the schema`);
      }
      try {
        (result as any).answer = zodSchema.parse(candidate);
      } catch (error) {
        throw new Error(`Agent answer schema validation failed: ${error instanceof Error ? error.message : String(error)}`);
      }
    }

    return result;
  }

  /**
   * Watch logs and wait for completion - mirrors Python watch_logs_and_wait
   */
  private async watchLogsAndWait(log: boolean = true, updateHandler: AgentUpdateHandler | null = null): Promise<LegacyAgentStatusResponse> {
    if (this.existingAgent) {
      throw new Error('You cannot call watchLogsAndWait() on an agent instantiated from agent id');
    }

    if (!this.response) {
      throw new Error('Agent not started');
    }

    const deadline = Date.now() + 300000;
    try {
      const result = await this.watchLogs(log, updateHandler, deadline);
      if (result && result.status !== 'active') {
        return result;
      }
    } catch (error) {
      console.warn(`[Agent] ${this.agentId} log stream unavailable; polling for completion.`);
    }
    // Losing the log transport does not mean execution has completed.
    while (Date.now() < deadline) {
      const result = await this.status(AbortSignal.timeout(Math.max(1, deadline - Date.now())));
      if (result.status !== 'active') {
        updateHandler?.({ type: 'completion', data: result, timestamp: new Date().toISOString() });
        return result;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    throw new Error(`Agent ${this.agentId} did not complete before the polling timeout; retrieve status() later.`);
  }

  /**
   * Watch logs via WebSocket - mirrors Python watch_logs method
   */
  private async watchLogs(log: boolean = true, updateHandler: AgentUpdateHandler | null = null, deadline = Date.now() + 300000): Promise<LegacyAgentStatusResponse | null> {
    if (this.existingAgent) {
      throw new Error('You cannot call watchLogs() on an agent instantiated from agent id');
    }

    if (!this.response) {
      throw new Error('Agent not started');
    }

    const config = this.client.getConfig();
    // Relative HTTP proxies do not expose the backend WebSocket transport.
    if (config.baseUrl?.startsWith('/')) return null;
    const agentId = this.response.agent_id;
    const sessionId = this.response.session_id;

    // Use the server-issued, session-scoped expiring viewer token, not the API key.
    const debug = await sessionDebugInfo({
      client: this.client.getClient(),
      path: { session_id: sessionId },
      throwOnError: true,
      signal: AbortSignal.timeout(Math.max(1, deadline - Date.now())),
    });
    const wsUrl = new URL(debug.data.ws.logs);
    const token = wsUrl.searchParams.get('token');
    if (!token || token === config.apiKey || wsUrl.protocol !== 'wss:') return null;
    wsUrl.pathname = `/agents/${encodeURIComponent(agentId)}/debug/logs`;
    wsUrl.searchParams.set('session_id', sessionId);

    return new Promise((resolve, reject) => {
      this.websocket = new WebSocket(wsUrl);
      const socket = this.websocket;
      const timeout = setTimeout(() => finish(null), Math.max(0, deadline - Date.now()));
      let settled = false;
      const finish = (result: LegacyAgentStatusResponse | null) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        if (this.websocket === socket) this.websocket = null;
        if (socket.readyState !== WebSocket.CLOSED) socket.terminate();
        resolve(result);
      };
      let counter = 0;

      this.websocket.on('open', () => {
        // Connection established
      });

      this.websocket.on('error', (error) => {
        console.error(`Connection error: ${agentId} ${error.message}`);
        finish(null);
      });

      this.websocket.on('message', (data) => {
        try {
          const message = data.toString();

          // Try to parse as JSON first
          let parsed: any;
          try {
            parsed = JSON.parse(message);
          } catch {
            // Not valid JSON, skip
            return;
          }

          // Check for termination: the final message is either a wrapped
          // { status: "agent_stop", agent: LegacyAgentStatusResponse } or the
          // raw LegacyAgentStatusResponse, depending on backend version.
          // Step messages have a "type" field (e.g. "agent_step_start", "observation")
          // and do NOT have "task" or "status" at the top level.
          const finalStatus = parseAgentStatusMessage(parsed, agentId);
          if (finalStatus) {
            // Call updateHandler for completion if provided
            if (updateHandler) {
              updateHandler({
                type: 'completion',
                data: finalStatus,
                timestamp: new Date().toISOString()
              });
            } else if (!finalStatus.success) {
              console.error(finalStatus.answer);
            }

            finish(finalStatus);
            return;
          }

          // Regular step update
          if (log) {
            counter++;

            // Use custom updateHandler if provided, otherwise use default logger
            if (updateHandler) {
              updateHandler({
                type: 'step',
                data: parsed,
                timestamp: new Date().toISOString()
              });
            } else {
              // Use the default logger function which mimics Python's live_log_state
              defaultStepLogger(parsed, counter, agentId);
            }
          }

        } catch (error) {
          console.error(`Error processing WebSocket message: ${error}`);
        }
      });

      this.websocket.on('close', () => {
        finish(null);
      });
    });
  }

  /**
   * Get agent status - mirrors Python status method
   */
  async status(signal?: AbortSignal): Promise<LegacyAgentStatusResponse> {
    if (!this.response) {
      throw new Error('Agent not started or not accessible');
    }

    const response = await agentStatus({
      client: this.client.getClient(),
      signal,
      path: {
        agent_id: this.response.agent_id
      }
    });

    if (response?.error) {
      throw new Error(`Failed to get agent status: ${formatError(response.error)}`);
    }

    return response.data as LegacyAgentStatusResponse;
  }

  /**
   * Stop the agent - mirrors Python stop method
   */
  async stop(): Promise<AgentResponse> {
    if (this.existingAgent) {
      throw new Error('You cannot call stop() on an agent instantiated from agent id');
    }

    if (!this.response) {
      throw new Error('Agent not started');
    }

    try {
      console.log(`[Agent] ${this.response.agent_id} is stopping`);

      const response = await agentStop({
        client: this.client.getClient(),
        path: {
          agent_id: this.response.agent_id
        },
        query: { session_id: this.response.session_id }
      });

      if (response?.error) {
        throw new Error(`Failed to stop agent: ${formatError(response.error)}`);
      }

      console.log(`[Agent] ${this.response.agent_id} stopped`);
      return response.data as AgentResponse;

    } catch (error) {
      console.warn(`Failed to stop agent: ${error instanceof Error ? error.message : String(error)}`);
      throw error;
    } finally {
      this.disconnectWebSocket();
    }
  }

  /**
   * Disconnect WebSocket
   */
  private disconnectWebSocket(): void {
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
  }

  /**
   * Get agent ID - mirrors Python agent_id property
   */
  get agentId(): string {
    if (!this.response) {
      throw new Error('You need to run the agent first to get the agent id');
    }
    return this.response.agent_id;
  }

  /**
   * Get session ID - mirrors Python session_id property
   */
  get sessionId(): string {
    if (!this.response) {
      throw new Error('You need to run the agent first to get the session id');
    }
    return this.response.session_id;
  }

  /**
   * Check if agent is running - convenience method
   */
  isRunning(): boolean {
    return this.response !== null;
  }
}
