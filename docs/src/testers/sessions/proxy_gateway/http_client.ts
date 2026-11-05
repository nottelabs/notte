// @sniptest filename=http_client.ts
// @sniptest typecheck_only=true
import https from 'node:https';

const response = await fetch('https://api.notte.cc/proxies/gateway/credentials', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${process.env.NOTTE_API_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ country: 'us' }),
});
if (!response.ok) throw new Error(`Minting failed: HTTP ${response.status}`);
const credential = (await response.json()) as { proxy_url_tls: string };

// Requests made with this agent exit from a residential IP in the US (Node.js 24.5+)
const agent = new https.Agent({ proxyEnv: { HTTPS_PROXY: credential.proxy_url_tls } });
https.get('https://api.ipify.org', { agent }, (res) => {
  res.setEncoding('utf8');
  res.on('data', (chunk: string) => process.stdout.write(chunk));
});
