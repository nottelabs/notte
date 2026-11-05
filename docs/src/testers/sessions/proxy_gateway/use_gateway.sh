# Mint a credential, then send a request through it
PROXY_URL=$(curl -sf -X POST https://api.notte.cc/proxies/gateway/credentials \
  -H "Authorization: Bearer $NOTTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"country": "us"}' | jq -er '.proxy_url_tls') || {
  echo "could not mint a gateway credential" >&2
  exit 1
}

curl --proxy "$PROXY_URL" https://api.ipify.org
