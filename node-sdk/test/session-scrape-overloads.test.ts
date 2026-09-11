/** `session.scrape()` overloads and passthrough. Mirrors `tests/sdk/test_scrape_overload_typing.py`. */
import { beforeEach, describe, it, expect, expectTypeOf, vi } from 'vitest';
import { z } from 'zod';
import { Session } from '@/session';
import { ScrapeFailedError } from '@/errors';
import type { ScrapeResult, StructuredData } from '@/scrape';
import { pageScrape, sessionStart } from '@/lib/client/sdk.gen';
import type { DataSpace, ImageData } from '@/lib/client/types.gen';
import { mockNotteClient, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
  pageScrape: vi.fn(),
}));

const Profile = z.object({ name: z.string(), age: z.number() });
type Profile = z.infer<typeof Profile>;

const images: ImageData[] = [{ url: 'https://example.com/a.png', category: 'content_image', description: 'a' }];

function dataSpace(overrides: Partial<DataSpace> = {}): DataSpace {
  return { markdown: '# Hello', images, structured: { success: true, error: null, data: { name: 'Ada', age: 36 } }, ...overrides };
}

async function startedSession(response: DataSpace): Promise<Session> {
  vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse() } as never);
  vi.mocked(pageScrape).mockResolvedValue({ data: response } as never);
  const session = new Session(mockNotteClient());
  await session.start();
  return session;
}

describe('session.scrape overloads', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('reveals the expected return types', () => {
    void ((session: Session) => {
      expectTypeOf(session.scrape({ response_format: Profile })).toEqualTypeOf<Promise<Profile>>();
      expectTypeOf(session.scrape({ response_format: Profile, instructions: 'x' })).toEqualTypeOf<Promise<Profile>>();
      expectTypeOf(session.scrape({ response_format: Profile, raiseOnFailure: true })).toEqualTypeOf<Promise<Profile>>();
      expectTypeOf(session.scrape({ response_format: Profile, raiseOnFailure: false })).toEqualTypeOf<Promise<StructuredData<Profile>>>();
      expectTypeOf(session.scrape({ only_images: true })).toEqualTypeOf<Promise<ImageData[]>>();
      expectTypeOf(session.scrape()).toEqualTypeOf<Promise<string>>();
      expectTypeOf(session.scrape({ only_main_content: true, selector: 'article' })).toEqualTypeOf<Promise<string>>();
      expectTypeOf(session.scrape({ instructions: 'Extract the company name' })).toEqualTypeOf<Promise<ScrapeResult<unknown>>>();
      expectTypeOf(session.scrape({ response_format: { type: 'object' } })).toEqualTypeOf<Promise<ScrapeResult<unknown>>>();
    });
  });

  it('returns markdown by default and passes the request through untouched', async () => {
    const session = await startedSession(dataSpace());
    expect(await session.scrape({ only_main_content: true, selector: 'article' })).toBe('# Hello');
    expect(pageScrape).toHaveBeenCalledWith(
      expect.objectContaining({ path: { session_id: 'session-123' }, body: { only_main_content: true, selector: 'article' } }),
    );
  });

  it('returns the images with only_images', async () => {
    const session = await startedSession(dataSpace());
    expect(await session.scrape({ only_images: true })).toEqual(images);
  });

  it('sends the zod schema as JSON schema and never invents instructions', async () => {
    const session = await startedSession(dataSpace());

    expect(await session.scrape({ response_format: Profile })).toEqual({ name: 'Ada', age: 36 });

    const call = vi.mocked(pageScrape).mock.calls[0][0] as { body: Record<string, unknown> };
    expect(call.body.response_format).toEqual(z.toJSONSchema(Profile));
    expect(call.body).not.toHaveProperty('instructions');
    expect(call.body).not.toHaveProperty('raiseOnFailure');
    expect(call.body).not.toHaveProperty('json_schema');
  });

  it('sends the instructions exactly as given', async () => {
    const session = await startedSession(dataSpace());
    await session.scrape({ response_format: Profile, instructions: 'Extract the profile' });
    expect(pageScrape).toHaveBeenCalledWith(expect.objectContaining({ body: expect.objectContaining({ instructions: 'Extract the profile' }) }));
  });

  it('validates the extracted data with the zod schema', async () => {
    const session = await startedSession(dataSpace({ structured: { success: true, data: { name: 'Ada', age: 'old' } } }));
    await expect(session.scrape({ response_format: Profile })).rejects.toThrow();
  });

  it('throws ScrapeFailedError on a failed extraction by default', async () => {
    const session = await startedSession(dataSpace({ structured: { success: false, error: 'no profile', data: null } }));
    await expect(session.scrape({ response_format: Profile })).rejects.toBeInstanceOf(ScrapeFailedError);
    await expect(session.scrape({ instructions: 'x' })).rejects.toThrow('no profile');
  });

  it('returns the StructuredData wrapper with raiseOnFailure false', async () => {
    const failed = await startedSession(dataSpace({ structured: { success: false, error: 'no profile', data: null } }));
    expect(await failed.scrape({ response_format: Profile, raiseOnFailure: false })).toEqual({ success: false, error: 'no profile', data: null });

    const ok = await startedSession(dataSpace());
    const result = await ok.scrape({ response_format: Profile, raiseOnFailure: false });
    expect(result.success).toBe(true);
    expect(result.data).toEqual({ name: 'Ada', age: 36 });
  });

  it('returns the raw structured data with instructions only', async () => {
    const session = await startedSession(dataSpace());
    expect(await session.scrape({ instructions: 'Extract the profile' })).toEqual({ name: 'Ada', age: 36 });
  });

  it('rejects when the session is not started', async () => {
    await expect(new Session(mockNotteClient()).scrape()).rejects.toThrow('Session not started');
    expect(pageScrape).not.toHaveBeenCalled();
  });
});
