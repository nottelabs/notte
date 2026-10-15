// @sniptest filename=notte_stagehand.ts
// @sniptest typecheck_only=true
import { NotteClient } from 'notte-sdk';
import { localBrowser, Stagehand } from '@browserbasehq/stagehand';
import { z } from 'zod';

export const result = await new NotteClient().Session().use(async (session) => {
  const browser = await localBrowser.connect({ cdpUrl: await session.cdpUrl() });
  try {
    const stagehand = await Stagehand.create({
      browser,
      model: {
        modelName: 'anthropic/claude-sonnet-4-6',
        apiKey: process.env.ANTHROPIC_API_KEY!,
      },
    });
    try {
      const page = await browser.context.newPage();
      await page.goto('https://example.com');
      const result = await stagehand.extract(
        'Extract the main heading', z.object({ heading: z.string() }), { page },
      );
      console.log(result.data.heading);
      return { heading: result.data.heading, session_id: session.getId()! };
    } finally {
      await stagehand.close();
    }
  } finally {
    await browser.close();
  }
});
