// @sniptest filename=shared_exit_session.ts
// @sniptest typecheck_only=true
import { readFileSync } from 'node:fs';
import { NotteClient, type NotteProxy, type SecretProxy } from 'notte-sdk';

const client = new NotteClient();

// Same sticky_session and country as the gateway credential.
// sticky_session is not in the published NotteProxy type yet.
const exit: NotteProxy & { sticky_session: string } = {
  type: 'notte',
  country: 'us',
  sticky_session: 'checkout-4821',
};

const secret: SecretProxy = {
  type: 'secret',
  server: 'https://secret-proxy.example.com:443',
  username: 'YOUR_PROXY_USERNAME',
  password: 'YOUR_PROXY_PASSWORD',
  ca_certificate: readFileSync('your-ca.pem', 'utf8'),
  hosts: ['api.stripe.com'],
};

await client.Session({ proxies: [exit, secret] }).use(async (session) => {
  console.log(session.getId());
});
