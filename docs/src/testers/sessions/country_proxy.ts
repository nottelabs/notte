// @sniptest filename=country_proxy.ts
// @sniptest show=1-7
import { NotteClient, type NotteProxy } from 'notte-sdk';

const client = new NotteClient();

// Route the session through a French residential proxy
const proxies: NotteProxy[] = [{ type: 'notte', country: 'fr' }];
const session = client.Session({ proxies });

const results = [proxies[0].type, proxies[0].country];
export { results, session };
