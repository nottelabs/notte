// @sniptest filename=vgs_session.ts
// @sniptest typecheck_only=true
import { readFileSync } from 'node:fs';
import { NotteClient, type SecretProxy } from 'notte-sdk';

const client = new NotteClient();

const vgs: SecretProxy = {
  type: 'secret',
  server: 'https://tntXXXXXXXXX.sandbox.verygoodproxy.com:8443',
  username: 'YOUR_VGS_ACCESS_CREDENTIAL_USERNAME',
  password: 'YOUR_VGS_ACCESS_CREDENTIAL_PASSWORD',
  // The VGS certificate from your dashboard's "Code snippets" section
  ca_certificate: readFileSync('sandbox.pem', 'utf8'),
  hosts: ['api.stripe.com'],
};

await client.Session({ proxies: [{ type: 'notte', country: 'us' }, vgs] }).use(async (session) => {
  console.log(session.getId());
});
