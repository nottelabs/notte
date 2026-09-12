// @sniptest filename=country_proxy.ts
// @sniptest show=1-3
import type { NotteProxy } from 'notte-sdk';

const proxies: NotteProxy = { type: 'notte', country: 'fr' };

const results = [proxies.type, proxies.country];
export { results };
