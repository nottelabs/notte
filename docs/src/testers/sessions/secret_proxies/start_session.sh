curl -X POST https://api.notte.cc/sessions/start \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "proxies": [
      {"type": "notte", "country": "us"},
      {
        "type": "secret",
        "server": "https://secret-proxy.example.com:443",
        "username": "YOUR_PROXY_USERNAME",
        "password": "YOUR_PROXY_PASSWORD",
        "ca_certificate": "-----BEGIN CERTIFICATE-----\nMIIF...\n-----END CERTIFICATE-----\n",
        "hosts": ["api.stripe.com", "*.adyen.com"]
      }
    ]
  }'
