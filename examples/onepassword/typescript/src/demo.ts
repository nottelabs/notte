import { createClient, Secrets } from '@1password/sdk';
import { NotteClient } from 'notte-sdk';
import { chromium, type Page, type Browser } from 'playwright-core';

class VaultFormError extends Error {}

export async function fillLogin(page: Page, usernameRef: string, passwordRef: string) {
  const token = process.env.OP_SERVICE_ACCOUNT_TOKEN;
  if (!token) throw new Error('Set OP_SERVICE_ACCOUNT_TOKEN');
  const vault = await createClient({
    auth: token,
    integrationName: 'Notte browser example', integrationVersion: '1.0.0',
  });
  const username = await vault.secrets.resolve(usernameRef);
  const password = await vault.secrets.resolve(passwordRef);
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(password);
  if (await page.getByLabel('Username', { exact: true }).inputValue() !== username) throw new Error('Username was not filled');
  if (await page.getByLabel('Password', { exact: true }).inputValue() !== password) throw new Error('Password was not filled');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
}

export async function runDemo() {
  for (const name of ['OP_SERVICE_ACCOUNT_TOKEN', 'OP_USERNAME_REF', 'OP_PASSWORD_REF']) {
    if (!process.env[name]) throw new Error(`Set ${name}`);
  }
  for (const name of ['OP_USERNAME_REF', 'OP_PASSWORD_REF']) Secrets.validateSecretReference(process.env[name]!);
  const client = new NotteClient();
  let sessionId = 'not-created';
  let stage = 'create browser';
  const safeError = (error: unknown) => {
    if (error instanceof VaultFormError) return error;
    const name = error instanceof Error ? error.constructor.name : 'UnknownError';
    const category = /^[A-Za-z][A-Za-z0-9]{0,63}$/.test(name) ? name : 'Error';
    return new VaultFormError(`Vault form failed: ${stage} [${category}] (session ${sessionId})`);
  };
  try {
    await client.Session({ max_duration_minutes: 3 }).use(async session => {
      sessionId = session.getId()!;
      stage = 'open test form';
      let browser: Browser | undefined;
      let failed = false, cleanupFailed = false;
      try {
        browser = await chromium.connectOverCDP(await session.cdpUrl());
        const page = browser.contexts()[0].pages()[0];
        await page.goto('about:blank');
        await page.setContent('<form onsubmit="event.preventDefault();document.querySelector(\'output\').textContent=\'Submitted\'"><label>Username<input name="username" autocomplete="off"></label><label>Password<input name="password" type="password" autocomplete="off"></label><button>Sign in</button><output></output></form>');
        stage = 'resolve and fill login';
        await fillLogin(page, process.env.OP_USERNAME_REF!, process.env.OP_PASSWORD_REF!);
        await page.locator('output').filter({ hasText: 'Submitted' }).waitFor();
      } catch (error) {
        failed = true;
        throw safeError(error);
      } finally {
        if (browser) {
          if (!failed) stage = 'disconnect browser';
          let timer: ReturnType<typeof setTimeout> | undefined;
          try {
            await Promise.race([
              browser.close(),
              new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Close deadline exceeded')), 5000); }),
            ]);
          } catch {
            cleanupFailed = true;
          } finally { clearTimeout(timer); }
        }
      }
      if (cleanupFailed) throw safeError(new Error('Browser disconnect failed'));
    });
    return { submitted: true, session_id: sessionId };
  } catch (error) {
    throw safeError(error);
  }
}
