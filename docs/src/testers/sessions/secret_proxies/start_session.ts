// @sniptest filename=start_session.ts
// @sniptest typecheck_only=true
import { readFileSync } from 'node:fs';
import { NotteClient, type NotteProxy, type SecretProxy } from 'notte-sdk';

const client = new NotteClient();

// The session's exit for every host you do not list
const exit: NotteProxy = { type: 'notte', country: 'us' };

// Your secret proxy, for the listed hosts only
const secret: SecretProxy = {
  type: 'secret',
  server: 'https://secret-proxy.example.com:443',
  username: 'YOUR_PROXY_USERNAME',
  password: 'YOUR_PROXY_PASSWORD',
  ca_certificate: readFileSync('your-ca.pem', 'utf8'),
  hosts: ['api.stripe.com', '*.adyen.com'],
};

await client.Session({ proxies: [exit, secret] }).use(async (session) => {
  // Server, hosts and CA fingerprints; never the credentials or the certificate
  const summary = session.getResponse()?.secret_proxy;
  if (summary) {
    console.log(summary.server, summary.hosts, summary.ca_sha256);
  }
});
