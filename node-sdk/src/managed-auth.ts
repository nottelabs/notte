import { setTimeout as delay } from 'node:timers/promises';
import type { NotteClient } from '@/client';
import { TIMEOUT_HEADER } from '@/client';
import { InvalidRequestError, NotteAPIError, NotteError, NotteTimeoutError } from '@/errors';
import type { SessionResponse as ApiSessionResponse } from '@/lib/client/types.gen';

// Lifecycle contracts are additive to the generated, pre-rollout API schema.
export type AuthSessionResponse = {
  [K in keyof ApiSessionResponse]: K extends 'status' ? ApiSessionResponse[K] | 'authenticating' : ApiSessionResponse[K];
};
export interface ManagedAuthOperation {
  id: string;
  connection_id: string;
  session_id?: string | null;
  source: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  phase: string;
  attempt: number;
  auth_retry: number;
  authenticated?: boolean | null;
  failure_code?: string | null;
  error?: string | null;
  deadline: string;
  created_at: string;
  updated_at: string;
}
export interface ManagedAuthReadiness {
  session_id: string;
  status: 'authenticating' | 'active' | 'failed' | 'closed';
  operations: ManagedAuthOperation[];
  error?: string | null;
}
export interface ManagedAuthRunResponse {
  operation_id?: string | null;
  authenticated?: boolean | null;
  connection_id: string;
  status: string;
  message: string;
}
export interface AuthWaitOptions {
  /** Overall waiting deadline, milliseconds. Defaults to 615000. */
  timeoutMs?: number;
  /** Delay between short polling requests, milliseconds. Defaults to 1000. */
  pollIntervalMs?: number;
  signal?: AbortSignal;
}
export interface ManagedAuthRunOptions extends AuthWaitOptions {
  /** Wait for completion. Defaults to true. */
  wait?: boolean;
  /** Additional server-side login attempts, from 0 to 2. Defaults to 0. */
  auth_retry?: number;
}
export class ManagedAuthError extends NotteError {}

export function validateAuthRetry(value: number): void {
  if (!Number.isInteger(value) || value < 0 || value > 2) {
    throw new InvalidRequestError('auth_retry must be an integer between 0 and 2');
  }
}

/** Poll read-only endpoints; never resubmit session creation or login. */
export async function pollAuth<T>(read: (signal: AbortSignal) => Promise<T | undefined>, options: AuthWaitOptions): Promise<T> {
  const timeoutMs = options.timeoutMs ?? 615_000;
  const interval = options.pollIntervalMs ?? 1000;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || !Number.isFinite(interval) || interval <= 0) {
    throw new InvalidRequestError('timeoutMs and pollIntervalMs must be positive finite numbers');
  }
  const deadline = new AbortController();
  const timer = setTimeout(() => deadline.abort(new NotteTimeoutError('Timed out waiting for authentication')), timeoutMs);
  // Forward caller cancellation without AbortSignal.any (unavailable in Node 20.0–20.2).
  const cancel = () => deadline.abort(options.signal?.reason);
  if (options.signal?.aborted) cancel();
  else options.signal?.addEventListener('abort', cancel, { once: true });
  const signal = deadline.signal;
  let errors = 0;
  try {
    while (true) {
      signal.throwIfAborted();
      try {
        const value = await read(signal);
        signal.throwIfAborted();
        if (value !== undefined) return value;
        errors = 0;
      } catch (error) {
        signal.throwIfAborted();
        const retryable = error instanceof NotteAPIError ? error.statusCode >= 500
          : error instanceof TypeError || error instanceof NotteTimeoutError;
        if (!retryable || ++errors >= 3) throw error;
      }
      await delay(interval, undefined, { signal });
    }
  } catch (error) {
    signal.throwIfAborted();
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', cancel);
  }
}

/**
 * Connection verification and recovery through `client.managedAuth`.
 *
 * ```typescript
 * const operation = await client.managedAuth.refreshConnection("<connection-id>", { wait: false });
 * await client.managedAuth.waitForAuth(operation);
 * ```
 */
export class NotteManagedAuth {
  constructor(private readonly client: NotteClient) {}

  /** Run only the verifier; this does not submit login credentials. */
  async checkConnection(connectionId: string): Promise<ManagedAuthRunResponse> {
    const response = await this.client.getClient().post<{ 200: ManagedAuthRunResponse }, unknown, true>({
      url: `/managed-auth/connections/${encodeURIComponent(connectionId)}/check`,
      body: {}, headers: { 'Content-Type': 'application/json' }, throwOnError: true,
    });
    return response.data;
  }

  async getOperation(operationId: string, options: Pick<AuthWaitOptions, 'signal'> = {}): Promise<ManagedAuthOperation> {
    const response = await this.client.getClient().get<{ 200: ManagedAuthOperation }, unknown, true>({
      url: `/managed-auth/operations/${encodeURIComponent(operationId)}`,
      headers: { [TIMEOUT_HEADER]: '10000' }, signal: options.signal, throwOnError: true,
    });
    return response.data;
  }

  /** Wait for an accepted operation. Aborting this wait does not cancel the server operation. */
  async waitForAuth(operation: ManagedAuthOperation, options: AuthWaitOptions = {}): Promise<ManagedAuthOperation> {
    const completed = (value: ManagedAuthOperation) => {
      if (value.status === 'succeeded') return value;
      if (value.status === 'pending' || value.status === 'running') return undefined;
      throw new ManagedAuthError(value.error || 'Connection authentication failed');
    };
    options.signal?.throwIfAborted();
    const result = completed(operation);
    if (result) return result;
    return pollAuth(async signal => completed(await this.getOperation(operation.id, { signal })), options);
  }

  /** Verify first, logging in only when required and automatic recovery is allowed. */
  async refreshConnection(connectionId: string, options: ManagedAuthRunOptions = {}): Promise<ManagedAuthOperation> {
    return this.run(connectionId, 'refresh', options);
  }

  /** Explicitly request a new login. Conflicting operations remain HTTP 409 errors. */
  async reauthenticateConnection(connectionId: string, options: ManagedAuthRunOptions = {}): Promise<ManagedAuthOperation> {
    return this.run(connectionId, 'reauthenticate', options);
  }

  private async run(connectionId: string, action: 'refresh' | 'reauthenticate', options: ManagedAuthRunOptions): Promise<ManagedAuthOperation> {
    const authRetry = options.auth_retry ?? 0;
    validateAuthRetry(authRetry);
    options.signal?.throwIfAborted();
    const response = await this.client.getClient().post<{ 202: ManagedAuthOperation }, unknown, true>({
      url: `/managed-auth/connections/${encodeURIComponent(connectionId)}/${action}`,
      body: { auth_retry: authRetry }, headers: { 'Content-Type': 'application/json' },
      signal: options.signal, throwOnError: true,
    });
    return options.wait === false ? response.data : this.waitForAuth(response.data, options);
  }
}
