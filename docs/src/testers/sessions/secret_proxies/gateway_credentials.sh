curl -X POST https://api.notte.cc/proxies/gateway/credentials \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"country": "us", "sticky_session": "checkout-4821"}'
