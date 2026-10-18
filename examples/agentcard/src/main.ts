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
}

type CleanupError = 'checkout_cancel' | 'page_close' | 'browser_close' | 'session_stop';

interface CheckoutResult {
  status: CheckoutState['status'];
  order_id: string | undefined;
  session_id: string;
  cleanup_errors?: CleanupError[];
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
      await client.Session({ max_duration_minutes: 20, idle_timeout_minutes: 20, proxies: false }).use(async session => {
        try {
          const browser = await connect(await session.cdpUrl());
          try {
            const context = browser.contexts()[0];
            if (!context) throw new Error('The owned session has no browser context');
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
                const result = await checkout.reconcile();
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
