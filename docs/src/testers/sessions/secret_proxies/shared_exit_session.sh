curl -X POST https://api.notte.cc/sessions/start \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "proxies": [
      {"type": "notte", "country": "us", "sticky_session": "checkout-4821"},
      {"type": "secret"}
    ]
  }'
