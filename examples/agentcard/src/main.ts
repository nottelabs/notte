import { attachToPlaywright, type Agentcard, type CheckoutState, type MerchantResult } from '@agent-cards/sdk';
import { NotteClient } from 'notte-sdk';
import { chromium, type Page } from 'playwright-core';

export interface CheckoutOptions {
  vault: Agentcard;
  userId: string;
  merchant: string;
  amount: number;
  currency: string;
  onApprovalUrl: (url: string) => void;
  purchase: (page: Page) => Promise<void>;
  readMerchantOrder: (page: Page, state: Readonly<CheckoutState>) => Promise<MerchantResult>;
}

interface Runtime {
  client: NotteClient;
  connect: typeof chromium.connectOverCDP;
  attach: typeof attachToPlaywright;
  approvalWaitMs: number;
  sessionMinutes: number;
}

const BLOCK_SERVICE_WORKERS =
  'try { if (navigator.serviceWorker) navigator.serviceWorker.register = async () => undefined; } catch {}';

type CleanupError = 'checkout_cancel' | 'page_close' | 'browser_close' | 'session_stop';

interface CheckoutResult {
  status: CheckoutState['status'];
  order_id: string | undefined;
  session_id: string;
  cleanup_errors?: CleanupError[];
}

type Checkout = Awaited<ReturnType<typeof attachToPlaywright>>;

// Agentcard expires an unapproved payment after 15 minutes; wait slightly longer so its own outcome lands first.
const APPROVAL_WAIT_MS = 16 * 60_000;
const PAUSED = /paused request/i;
// Notte's session cap on standard plans; the approval wait is clipped to fit inside it.
const SESSION_MINUTES = 30;
// No session operation runs while the user approves, so the idle timeout must exceed the approval wait.
const SESSION_IDLE_MINUTES = 30;
// Time kept after the approval wait to read the merchant order and close the session.
const RECONCILE_MARGIN_MS = 2 * 60_000;

// The card request stays paused until the user approves or declines on their device.
// Reconciling before that request finishes is rejected by the SDK, so wait for it first.
async function reconcileAfterApproval(checkout: Checkout, deadline: number) {
  for (;;) {
    if (checkout.getState().status !== 'awaiting_approval') {
      try { return await checkout.reconcile(); }
      catch (error) { if (!PAUSED.test(String((error as Error)?.message))) throw error; }
    }
    if (Date.now() >= deadline) throw new Error('The approval wait ended before the paused payment finished');
    await new Promise(resolve => setTimeout(resolve, 1_000));
  }
}

async function closeTransport(close: () => Promise<void>) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([close(), new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error('Browser disconnect timed out')), 5_000);
    })]);
  } finally { clearTimeout(timer); }
}

export async function runCheckout(options: CheckoutOptions, runtime: Partial<Runtime> = {}): Promise<CheckoutResult> {
  const approvalWaitMs = runtime.approvalWaitMs ?? APPROVAL_WAIT_MS;
  const sessionMinutes = runtime.sessionMinutes ?? SESSION_MINUTES;
  const client = runtime.client ?? new NotteClient();
  const connect = runtime.connect ?? chromium.connectOverCDP.bind(chromium);
  const attach = runtime.attach ?? attachToPlaywright;
  let reconciled: CheckoutResult | undefined;
  const cleanupErrors: CleanupError[] = [];
  const close = async (stage: 'page_close' | 'browser_close', action: () => Promise<void>) => {
    try { await closeTransport(action); }
    catch { cleanupErrors.push(stage); }
  };
  let step = 'Agentcard registry refresh';
  try {
    await options.vault.syncRegistry();
    step = 'Hosted checkout';
    try {
      await client.Session({ max_duration_minutes: sessionMinutes, idle_timeout_minutes: Math.min(SESSION_IDLE_MINUTES, sessionMinutes), proxies: false }).use(async session => {
        const sessionEndsAt = Date.now() + sessionMinutes * 60_000;
        try {
          const browser = await connect(await session.cdpUrl());
          try {
            const context = browser.contexts()[0];
            if (!context) throw new Error('The owned session has no browser context');
            // A store's service worker can send the card request itself, and Playwright cannot pause it.
            await context.addInitScript(BLOCK_SERVICE_WORKERS);
            const page = await context.newPage();
            try {
              const checkout = await attach(page, {
                vault: options.vault,
                user: options.userId,
                merchant: options.merchant,
                amount: options.amount,
                currency: options.currency,
                onApprovalUrl: options.onApprovalUrl,
                requireMerchantResult: true,
                resolveMerchantResult: state => options.readMerchantOrder(page, state),
              });
              try {
                await options.purchase(page);
                const deadline = Math.min(Date.now() + approvalWaitMs, sessionEndsAt - RECONCILE_MARGIN_MS);
                const result = await reconcileAfterApproval(checkout, deadline);
                reconciled = { status: result.status, order_id: result.orderId, session_id: session.getId()! };
                return reconciled;
              } finally {
                try { checkout.cancel(); }
                catch { cleanupErrors.push('checkout_cancel'); }
              }
            } finally { await close('page_close', () => page.close()); }
          } finally { await close('browser_close', () => browser.close()); }
        } catch {
          throw new Error('Hosted checkout failed; verify the merchant outcome before attempting another payment');
        }
      });
    } catch {
      if (!reconciled) throw new Error('Hosted checkout failed; verify the merchant outcome before attempting another payment');
      cleanupErrors.push('session_stop');
    }
    if (!reconciled) throw new Error('Checkout did not reconcile');
    return { ...reconciled, ...(cleanupErrors.length ? { cleanup_errors: cleanupErrors } : {}) };
  } catch {
    throw new Error(`${step} failed; verify the merchant outcome before attempting another payment`);
  }
}
