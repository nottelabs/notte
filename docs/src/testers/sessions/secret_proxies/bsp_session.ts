// @sniptest filename=bsp_session.ts
// @sniptest typecheck_only=true
import { readFileSync } from 'node:fs';
import { NotteClient, type NotteProxy, type SecretProxy } from 'notte-sdk';

const client = new NotteClient();

// The session's exit for every host you do not list
const exit: NotteProxy = { type: 'notte', country: 'us' };

const secret: SecretProxy = {
  type: 'secret',
  // The TLS terminator in front of browser-secret-proxy
  server: 'https://browser-secret-proxy.example.com:443',
  // SECRET_PROXY_USERNAME and SECRET_PROXY_PASSWORD
  username: 'proxy-user',
  password: 'a-long-random-password',
  // The CA from step 2, never its key
  ca_certificate: readFileSync('ca.pem', 'utf8'),
  // The same hosts as -hosts
  hosts: ['api.example.com'],
};

await client.Session({ proxies: [exit, secret] }).use(async (session) => {
  // The browser sends the stand-in; api.example.com receives the real value
  await session.execute({ type: 'goto', url: 'https://api.example.com/echo?token=tok_standin_123' });
});
