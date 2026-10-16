import Link from '@stripe/link-sdk';
import { NotteClient } from 'notte-sdk';
import { chromium, type Page } from 'playwright-core';

class LinkFormError extends Error {}

function safeFailure(error: unknown, stage: string, sessionId: string) {
  if (error instanceof LinkFormError) return error;
  const name = error instanceof Error ? error.constructor.name : 'UnknownError';
  const category = /^[A-Za-z][A-Za-z0-9]{0,63}$/.test(name) ? name : 'Error';
  const status = error && typeof error === 'object' && 'status' in error ? error.status : undefined;
  const detail = typeof status === 'number' && Number.isInteger(status) && status >= 100 && status <= 599 ? ` HTTP ${status}` : '';
  return new LinkFormError(`Link form failed: ${stage} [${category}]${detail} (session ${sessionId})`);
}

export async function fillApprovedTestCard(page: Page, wallet: Link, requestId: string) {
  const request = await wallet.spendRequests.retrieve(requestId, { include: ['card'] });
  if (!request || request.status !== 'approved' || !request.card) {
    throw new Error('The Link spend request needs approval and a card credential');
  }
  const card = request.card;
  // Link's published test credential. This example refuses real cards.
  if (card.number !== '4000009990001984' || !card.cvc) { // pragma: allowlist secret
    throw new Error('Use an approved Link test-mode card request');
  }
  const fields = { 'Card number': card.number, Expiry: `${String(card.exp_month).padStart(2, '0')}/${card.exp_year}`, CVC: card.cvc };
  for (const [label, value] of Object.entries(fields)) {
    await page.getByLabel(label, { exact: true }).fill(value);
    if (await page.getByLabel(label, { exact: true }).inputValue() !== value) throw new Error('A test card field was not filled');
  }
}

export async function runDemo(wallet?: Link) {
  for (const name of ['LINK_ACCESS_TOKEN', 'LINK_SPEND_REQUEST_ID']) {
    if (!process.env[name]) throw new Error(`Set ${name}`);
  }
  const client = new NotteClient();
  let sessionId = 'not-created';
  let stage = 'create browser';
  try {
    await client.Session({ max_duration_minutes: 3 }).use(async session => {
      sessionId = session.getId()!;
      stage = 'open test form';
      try {
        const browser = await chromium.connectOverCDP(await session.cdpUrl());
        try {
          const page = browser.contexts()[0].pages()[0];
          await page.goto('about:blank');
          await page.setContent('<label>Card number<input type="password" autocomplete="off"></label><label>Expiry<input autocomplete="off"></label><label>CVC<input type="password" autocomplete="off"></label>');
          stage = 'retrieve and fill approved test card';
          await fillApprovedTestCard(page, wallet ?? new Link({ accessToken: process.env.LINK_ACCESS_TOKEN! }), process.env.LINK_SPEND_REQUEST_ID!);
        } finally { await browser.close(); }
      } catch (error) { throw safeFailure(error, stage, sessionId); }
    });
    return { filled: true, session_id: sessionId };
  } catch (error) {
    throw safeFailure(error, stage, sessionId);
  }
}
