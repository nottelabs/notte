// @sniptest filename=playwright_dialogs.ts
// @sniptest show=1-21
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// 'client': your Playwright code answers dialogs, not Notte
const session = client.Session({ dialog_policy: 'client' });
const { title, status } = await session.use(async () => {
  const page = await session.page();

  // Register the handler before the page opens a dialog
  page.on('dialog', dialog => dialog.accept());

  await page.setContent(
    `<button onclick="document.title = confirm('Delete this item?') ? 'accepted' : 'dismissed'">Delete</button>`,
  );
  await page.click('button');
  const title = await page.title();
  console.log(title); // accepted
  return { title, status: await session.status() };
});

export { status, title };
