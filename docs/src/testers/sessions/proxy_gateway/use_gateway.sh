# Mint a credential, then send a request through it
PROXY_URL=$(curl -s -X POST https://api.notte.cc/proxies/gateway/credentials \
  -H "Authorization: Bearer $NOTTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"country": "us"}' | jq -r '.proxy_url_tls')

curl --proxy "$PROXY_URL" https://api.ipify.org
