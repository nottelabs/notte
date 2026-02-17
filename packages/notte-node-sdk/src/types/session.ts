import { z } from "zod";

// --- Proxy schemas ---

const NotteProxySchema = z.object({
  type: z.literal("notte"),
  id: z.string().nullable().optional(),
  country: z.string().nullable().optional(),
});

const ExternalProxySchema = z.object({
  type: z.literal("external"),
  server: z.string(),
  username: z.string().nullable().optional(),
  password: z.string().nullable().optional(),
  bypass: z.string().nullable().optional(),
});

const ProxySettingsSchema = z.discriminatedUnion("type", [
  NotteProxySchema,
  ExternalProxySchema,
]);

// --- Session profile ---

const SessionProfileSchema = z.object({
  id: z.string(),
  persist: z.boolean().optional(),
});

// --- Session start request ---

export const SessionStartRequestSchema = z
  .object({
    headless: z.boolean().optional(),
    solve_captchas: z.boolean().optional(),
    max_duration_minutes: z.number().int().positive().optional(),
    idle_timeout_minutes: z.number().int().positive().optional(),
    proxies: z.union([z.array(ProxySettingsSchema), z.boolean(), z.string()]).optional(),
    browser_type: z.string().optional(),
    user_agent: z.string().nullable().optional(),
    chrome_args: z.array(z.string()).nullable().optional(),
    viewport_width: z.number().int().nullable().optional(),
    viewport_height: z.number().int().nullable().optional(),
    cdp_url: z.string().nullable().optional(),
    use_file_storage: z.boolean().optional(),
    screenshot_type: z.string().optional(),
    profile: SessionProfileSchema.nullable().optional(),
    web_bot_auth: z.boolean().optional(),
  })
  .strict();

export type SessionStartRequest = z.infer<typeof SessionStartRequestSchema>;

// --- Session response ---

export const SessionResponseSchema = z
  .object({
    session_id: z.string(),
    idle_timeout_minutes: z.number().int(),
    max_duration_minutes: z.number().int(),
    created_at: z.string(),
    closed_at: z.string().nullable().optional(),
    last_accessed_at: z.string(),
    duration: z.unknown().optional(),
    status: z.enum(["active", "closed", "error", "timed_out"]),
    steps: z.array(z.record(z.unknown())).optional(),
    error: z.string().nullable().optional(),
    credit_usage: z.number().nullable().optional(),
    proxies: z.boolean().optional(),
    browser_type: z.string().optional(),
    use_file_storage: z.boolean().optional(),
    network_request_bytes: z.number().optional(),
    network_response_bytes: z.number().optional(),
    user_agent: z.string().nullable().optional(),
    viewport_width: z.number().nullable().optional(),
    viewport_height: z.number().nullable().optional(),
    headless: z.boolean().optional(),
    solve_captchas: z.boolean().nullable().optional(),
    cdp_url: z.string().nullable().optional(),
    viewer_url: z.string().nullable().optional(),
    web_bot_auth: z.boolean().optional(),
  })
  .passthrough();

export type SessionResponse = z.infer<typeof SessionResponseSchema>;

// --- Session list request ---

export const SessionListRequestSchema = z
  .object({
    only_active: z.boolean().optional(),
    page_size: z.number().int().optional(),
    page: z.number().int().optional(),
  })
  .strict();

export type SessionListRequest = z.infer<typeof SessionListRequestSchema>;
