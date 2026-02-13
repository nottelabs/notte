import { z } from "zod";

export const CookieSchema = z
  .object({
    name: z.string(),
    value: z.string(),
    domain: z.string(),
    path: z.string(),
    httpOnly: z.boolean(),
    expirationDate: z.number().nullable().optional(),
    hostOnly: z.boolean().nullable().optional(),
    sameSite: z.enum(["Lax", "None", "Strict"]).nullable().optional(),
    secure: z.boolean().nullable().optional(),
    session: z.boolean().nullable().optional(),
    storeId: z.string().nullable().optional(),
    expires: z.number().nullable().optional(),
    partitionKey: z.string().nullable().optional(),
  })
  .passthrough();

export type Cookie = z.infer<typeof CookieSchema>;

export const SetCookiesRequestSchema = z
  .object({
    cookies: z.array(CookieSchema),
  })
  .strict();

export type SetCookiesRequest = z.infer<typeof SetCookiesRequestSchema>;

export const SetCookiesResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
  })
  .passthrough();

export type SetCookiesResponse = z.infer<typeof SetCookiesResponseSchema>;

export const GetCookiesResponseSchema = z
  .object({
    cookies: z.array(CookieSchema),
  })
  .passthrough();

export type GetCookiesResponse = z.infer<typeof GetCookiesResponseSchema>;
