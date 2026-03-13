import { z } from "zod";
import { SessionResponseSchema } from "./session.js";

// --- Scrape ---

export const ScrapeRequestSchema = z
  .object({
    selector: z.string().nullable().optional(),
    scrape_links: z.boolean().optional(),
    scrape_images: z.boolean().optional(),
    ignored_tags: z.array(z.string()).nullable().optional(),
    only_main_content: z.boolean().optional(),
    only_images: z.boolean().optional(),
    response_format: z.record(z.unknown()).nullable().optional(),
    instructions: z.string().nullable().optional(),
    use_link_placeholders: z.boolean().optional(),
  })
  .strict();

export type ScrapeRequest = z.infer<typeof ScrapeRequestSchema>;

export const ScrapeResponseSchema = z
  .object({
    session: SessionResponseSchema,
    markdown: z.string().nullable().optional(),
    structured_data: z.unknown().nullable().optional(),
    images: z.array(z.unknown()).nullable().optional(),
    metadata: z.record(z.unknown()).optional(),
  })
  .passthrough();

export type ScrapeResponse = z.infer<typeof ScrapeResponseSchema>;

// --- Observe ---

export const ObserveRequestSchema = z
  .object({
    url: z.string().nullable().optional(),
    instructions: z.string().nullable().optional(),
    perception_type: z.string().nullable().optional(),
    min_nb_actions: z.number().int().nullable().optional(),
    max_nb_actions: z.number().int().optional(),
  })
  .strict();

export type ObserveRequest = z.infer<typeof ObserveRequestSchema>;

export const ObserveResponseSchema = z
  .object({
    session: SessionResponseSchema,
    metadata: z.record(z.unknown()).optional(),
    space: z.unknown().nullable().optional(),
    screenshot: z.unknown().nullable().optional(),
  })
  .passthrough();

export type ObserveResponse = z.infer<typeof ObserveResponseSchema>;

// --- Execute ---

export const ExecutionRequestSchema = z
  .object({
    type: z.string(),
    id: z.string().nullable().optional(),
    value: z.union([z.string(), z.number()]).nullable().optional(),
    enter: z.boolean().nullable().optional(),
    selector: z.unknown().nullable().optional(),
    url: z.string().optional(),
    key: z.string().optional(),
    milliseconds: z.number().optional(),
    path: z.string().optional(),
    script: z.string().optional(),
    tab_idx: z.number().optional(),
  })
  .strict();

export type ExecutionRequest = z.infer<typeof ExecutionRequestSchema>;

export const ExecutionResponseSchema = z
  .object({
    session: SessionResponseSchema,
    success: z.boolean().optional(),
    message: z.string().nullable().optional(),
    exception: z.string().nullable().optional(),
    url: z.string().nullable().optional(),
  })
  .passthrough();

export type ExecutionResponse = z.infer<typeof ExecutionResponseSchema>;
