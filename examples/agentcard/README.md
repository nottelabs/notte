# Agentcard with Notte

`runCheckout` attaches the current Agentcard SDK to the dedicated context of a newly created Notte session before your merchant automation runs. Your app supplies the checkout actions, a private approval-link delivery callback, and an authoritative merchant-order reader. It returns a status, optional confirmed order ID, and the stopped Notte session ID.

Requires Node.js 24+, `NOTTE_API_KEY`, and [Agentcard sandbox credentials](https://app.agentcard.sh). Run `npm ci`. Create `Agentcard` from `@agent-cards/sdk` with your sandbox `AGENTCARD_CLIENT_ID`, `AGENTCARD_CLIENT_SECRET`, and `sandbox: true`; pass it with `AGENTCARD_USER_ID` to the exported helper in `src/main.ts`. First link a test card to that user using the [Vault quickstart](https://docs.agentcard.sh/vault/quickstart).

Implement `purchase(page)` for your sandbox merchant. Deliver `onApprovalUrl` only through your application's private user channel. Implement `readMerchantOrder(page, state)` using the merchant's confirmation page or order API; approval alone does not confirm an order. The helper does not log payment details or approval URLs, record browser traces, or retry a payment.

Every result closes the page and owned session. No existing session or persistent profile is reused. For pending, unknown, or user-action outcomes, follow up through the merchant before starting another checkout. See [Agentcard's completion guide](https://docs.agentcard.sh/vault/completing-a-purchase).

Run `npm test` for adapter contracts. Set `NOTTE_AGENTCARD_LIVE=1` and an explicit `NOTTE_API_URL`, then run `npm run test:live` for real SDK attachment and browser cleanup without vendor calls or payments. SDK attachment and browser cleanup are validated; end-to-end sandbox approval, payment, and merchant confirmation have not been tested. Validate your merchant in sandbox before production.

The published SDK is used as an unmodified dependency under its license. No proprietary SDK implementation or data is included here.
