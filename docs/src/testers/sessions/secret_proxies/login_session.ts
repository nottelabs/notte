// @sniptest filename=login_session.ts
// @sniptest typecheck_only=true
import { readFileSync } from 'node:fs';
import { NotteClient, type NotteProxy, type SecretProxy } from 'notte-sdk';

const client = new NotteClient();

// Stand-ins from your provider or your own proxy. They are not secrets:
// the page, the agent, screenshots and network logs only contain these values.
const USERNAME = 'tok_user_7Hq2Xc';
const PASSWORD = 'tok_pwd_9Kd3Wm';
const OTP = 'tok_otp_4Lm8Rv';

const exit: NotteProxy = { type: 'notte', country: 'us' };

const secret: SecretProxy = {
  type: 'secret',
  server: 'https://secret-proxy.example.com:443',
  username: 'YOUR_PROXY_USERNAME',
  password: 'YOUR_PROXY_PASSWORD',
  ca_certificate: readFileSync('your-ca.pem', 'utf8'),
  // The host that receives the login and 2FA requests, not the app's host
  hosts: ['auth.example.com'],
};

await client.Session({ proxies: [exit, secret] }).use(async (session) => {
  await session.execute({ type: 'goto', url: 'https://app.example.com/login' });

  // The form posts to auth.example.com, where your proxy swaps the stand-ins
  await session.execute({ type: 'fill', selector: "input[name='username']", value: USERNAME });
  await session.execute({ type: 'fill', selector: "input[name='password']", value: PASSWORD });
  await session.execute({ type: 'click', selector: "button[type='submit']" });

  // 2FA step: the same stand-in every time; your proxy sends the current code
  await session.execute({ type: 'fill', selector: "input[name='otp']", value: OTP });
  await session.execute({ type: 'click', selector: "button[type='submit']" });
});
