import { describe, it, expect } from 'vitest';
import { NotteClient } from '@/client';
import { config } from 'dotenv';
config();

// Keep this small regression in the PR smoke suite as well as full live runs.
describe('Persona form integration', () => {
  it('should fill form with persona information', async () => {
    const client = new NotteClient();
    const persona = client.Persona({ create_vault: false, create_phone_number: false });
    let personaId: string | null = null;
    const session = client.Session({
      proxies: false,
      browser_type: 'chromium',
      viewport_width: 1280,
      viewport_height: 1080,
      headless: true,
    });
    const fixtureUrl = 'https://persona-fixture.notte.test/';

    try {
      await persona.get();
      personaId = persona.personaId;
      const firstName = persona.info?.first_name;
      const lastName = persona.info?.last_name;
      expect(firstName).toBeTruthy();
      expect(lastName).toBeTruthy();

      await session.use(async () => {
        const page = await session.page();
        // Serve the owned form and abort all other requests.
        await page.route('**/*', async route => {
          if (route.request().url() === fixtureUrl) {
            await route.fulfill({
              status: 200,
              contentType: 'text/html',
              body: '<!doctype html><html><body><h1>Persona form</h1><label for="full-name">Full name</label><input id="full-name" name="full_name" autocomplete="name"></body></html>',
            });
          } else {
            await route.abort();
          }
        });
        await page.goto(fixtureUrl, { waitUntil: 'domcontentloaded' });

        const agent = client.Agent({ session, max_steps: 5, persona });
        const response = await agent.run({
          task: "The form is already open. Fill the Full name field with your persona's first and last names. Do not submit or navigate. Finish and return the full name.",
        });

        expect(response.success).toBe(true);
        expect(response.answer).toContain(firstName);
        expect(response.answer).toContain(lastName);
        expect(await page.inputValue('#full-name')).toBe(`${firstName} ${lastName}`);
      });
    } finally {
      if (personaId) await client.Persona({ persona_id: personaId }).delete();
    }
  });
});
