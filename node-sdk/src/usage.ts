import type { NotteClient } from '@/client';
import type {
  GetUsageData,
  GetUsageLogsData,
  PaginatedResponseUsageLog,
  UsageLog,
  UsageResponse,
} from '@/lib/client/types.gen';
import { getUsage, getUsageLogs } from '@/lib/client/sdk.gen';

/** Options of `client.usage.get()`: the monthly period, e.g. `"May 2025"`. Defaults to the current month. */
export type UsageOptions = NonNullable<GetUsageData['query']>;
/** Options of `client.usage.logs()`: endpoint filter and pagination. */
export type UsageLogsOptions = NonNullable<GetUsageLogsData['query']>;
/** Endpoint names accepted by `UsageLogsOptions.endpoint`. */
export type UsageLogEndpoint = NonNullable<UsageLogsOptions['endpoint']>;

export type { PaginatedResponseUsageLog, UsageLog, UsageResponse };

/**
 * Usage and billing, the counterpart of `GET /usage` and `GET /usage/logs`.
 *
 * ```ts
 * const usage = await client.usage.get();
 * console.log(usage.total_cost, usage.balance_amount);
 * ```
 */
export class NotteUsage {
  private readonly client: NotteClient;

  constructor(client: NotteClient) {
    this.client = client;
  }

  /**
   * Usage summary for a monthly period (current month by default).
   *
   * ```ts
   * const usage = await client.usage.get({ period: 'May 2025' });
   * console.log(`${usage.session_count} sessions, $${usage.total_cost}`);
   * ```
   */
  async get(options: UsageOptions = {}): Promise<UsageResponse> {
    const response = await getUsage({ client: this.client.getClient(), query: options, throwOnError: true });
    return response.data;
  }

  /**
   * Paginated per-request usage logs, optionally filtered by endpoint.
   *
   * ```ts
   * const page = await client.usage.logs({ endpoint: 'sessions.start', page: 1, page_size: 50 });
   * page.items.forEach(log => console.log(log.created_at, log.endpoint, log.duration_ms));
   * ```
   */
  async logs(options: UsageLogsOptions = {}): Promise<PaginatedResponseUsageLog> {
    const response = await getUsageLogs({ client: this.client.getClient(), query: options, throwOnError: true });
    return response.data;
  }
}
